"""Web-based series browser for reviewing and rescuing photos.

Runs a local HTTP server (stdlib only, no dependencies) that shows
all processed series with thumbnails, scores, and a temporal browser
for finding nearby photos when the print shop detects an error.
"""
from __future__ import annotations

import hashlib
import io
import json
import secrets
import shutil
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from PIL import Image

from config_utils import save_config
from logger_setup import build_logger


# ---------------------------------------------------------------------------
# Autonomous monitoring state
# ---------------------------------------------------------------------------

class _MonitorState:
    """Global state for the INBOX monitoring thread."""
    thread: threading.Thread | None = None
    running: bool = False
    observer: object | None = None  # watchdog Observer
    series_count: int = 0
    last_activity: str = ""
    error: str = ""

    @classmethod
    def is_active(cls) -> bool:
        return cls.running and cls.thread is not None and cls.thread.is_alive()

    @classmethod
    def status_dict(cls) -> dict:
        return {
            "active": cls.is_active(),
            "series_processed": cls.series_count,
            "last_activity": cls.last_activity,
            "error": cls.error,
        }


def _start_monitoring(config: dict) -> None:
    """Start watching the incoming folder in a background thread."""
    if _MonitorState.is_active():
        return

    from watcher import (
        IncomingFolderHandler,
        PendingQueue,
        group_files_by_time,
    )
    from face_utils import MediaPipeFaceAnalyzer
    from selector import process_series
    from sheet_composer import compose_pending_sheets

    try:
        from watchdog.observers import Observer
    except ImportError:
        _MonitorState.error = "watchdog не установлен"
        return

    incoming_dir = Path(config["paths"]["input_folder"])
    if not incoming_dir.is_absolute():
        from config_utils import get_project_root
        incoming_dir = get_project_root() / incoming_dir
    incoming_dir.mkdir(parents=True, exist_ok=True)

    _MonitorState.error = ""
    _MonitorState.series_count = 0
    _MonitorState.running = True
    _MonitorState.last_activity = ""

    def monitor_loop() -> None:
        logger = build_logger(config["paths"]["log_dir"])
        logger.info("Автономный режим: мониторинг %s", incoming_dir)

        analyzer = MediaPipeFaceAnalyzer(config["thresholds"]["min_face_confidence"])
        pending = PendingQueue()
        observer = Observer()
        observer.schedule(IncomingFolderHandler(pending), str(incoming_dir), recursive=False)
        observer.start()
        _MonitorState.observer = observer

        series_idx = 1
        try:
            while _MonitorState.running:
                ready = pending.flush_ready(config["series_detection"]["cooldown_seconds"])
                if ready:
                    grouped = group_files_by_time(ready, config["series_detection"]["max_gap_seconds"])
                    for group in grouped:
                        if not _MonitorState.running:
                            break
                        process_series(
                            group, series_idx, analyzer, config, logger,
                            remove_source_files=False, save_annotations=True,
                        )
                        compose_pending_sheets(config, logger)
                        _MonitorState.series_count += 1
                        _MonitorState.last_activity = time.strftime("%H:%M:%S")
                        # Invalidate series cache
                        SeriesBrowserHandler._series_cache = None
                        series_idx += 1
                time.sleep(0.5)
        except Exception as exc:
            _MonitorState.error = str(exc)
        finally:
            observer.stop()
            observer.join()
            analyzer.close()
            _MonitorState.running = False

    _MonitorState.thread = threading.Thread(target=monitor_loop, daemon=True)
    _MonitorState.thread.start()


def _stop_monitoring() -> None:
    """Stop the incoming folder monitoring thread."""
    _MonitorState.running = False
    if _MonitorState.observer is not None:
        try:
            _MonitorState.observer.stop()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Auth session store (in-memory, simple token-based)
# ---------------------------------------------------------------------------

_auth_tokens: set[str] = set()


def _make_token() -> str:
    """Generate a random auth token."""
    return secrets.token_hex(16)


def _check_auth_cookie(cookie_header: str | None) -> bool:
    """Check if the request has a valid auth cookie."""
    if not cookie_header:
        return False
    for part in cookie_header.split(";"):
        part = part.strip()
        if part.startswith("kanatka_auth="):
            token = part.split("=", 1)[1]
            return token in _auth_tokens
    return False


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def load_all_series(log_dir: Path) -> list[dict]:
    """Read all ser*_report.json files and return sorted list of series."""
    series: list[dict] = []
    for report_path in sorted(log_dir.glob("ser*_report.json")):
        try:
            data = json.loads(report_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict) and "series" in data:
            series.append(data)
    return series


def rescue_photo(source_path: Path, selected_dir: Path, series_name: str) -> Path:
    """Copy a photo into the selected directory with series prefix."""
    selected_dir.mkdir(parents=True, exist_ok=True)
    dest_name = f"{series_name}_{source_path.name}"
    dest = selected_dir / dest_name
    shutil.copy2(source_path, dest)
    return dest


def rescue_batch(
    photos: list[dict],
    selected_dir: Path,
    config: dict,
) -> list[Path]:
    """Copy multiple photos to selected/ and sync to network if enabled.

    Each item in photos: {"path": str, "series": str}
    Returns list of destination paths.
    """
    selected_dir.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for item in photos:
        source = Path(item["path"])
        if not source.exists():
            # Try INBOX fallback
            inbox = Path(config["paths"]["test_photos_folder"])
            if not inbox.is_absolute():
                inbox = Path.cwd() / inbox
            source = inbox / Path(item["path"]).name
        if not source.exists():
            continue
        series_name = item["series"]
        dest_name = f"{series_name}_{source.name}"
        dest = selected_dir / dest_name
        if not dest.exists():
            shutil.copy2(source, dest)
            copied.append(dest)

    # Auto-sync rescued photos to network if enabled
    if copied:
        _sync_rescued_to_network(copied, config)

    return copied


def _sync_rescued_to_network(files: list[Path], config: dict) -> int:
    """Copy rescued files to network folder if auto_sync is enabled."""
    network_config = config.get("network", {})
    if not network_config.get("auto_sync_sheets", False):
        return 0
    network_path = network_config.get("output_path", "")
    if not network_path:
        return 0
    target = Path(network_path)
    try:
        if not target.exists():
            return 0
    except OSError:
        return 0
    synced = 0
    for f in files:
        dest = target / f.name
        if not dest.exists():
            try:
                shutil.copy2(f, dest)
                synced += 1
            except OSError:
                pass
    return synced


def _count_ambiguous_series() -> int:
    """Count series with ambiguous_manual_review status from report JSONs."""
    try:
        from config_utils import load_config
        config = load_config()
        log_dir = Path(config["paths"]["log_dir"])
    except Exception:
        return 0
    count = 0
    for report_path in log_dir.glob("ser*_report.json"):
        try:
            data = json.loads(report_path.read_text(encoding="utf-8"))
            if data.get("status") == "ambiguous_manual_review":
                count += 1
        except (json.JSONDecodeError, OSError):
            pass
    return count


def confirm_ambiguous(series_name: str, config: dict) -> bool:
    """Move the ambiguous series photo from ambiguous/ to selected/.

    Returns True on success.
    """
    ambiguous_dir = Path(config["paths"].get("output_ambiguous", "workdir/ambiguous"))
    selected_dir = Path(config["paths"]["output_selected"])
    selected_dir.mkdir(parents=True, exist_ok=True)

    for f in ambiguous_dir.glob(f"{series_name}_*"):
        dest = selected_dir / f.name
        shutil.move(str(f), str(dest))
        return True
    return False


def _find_photo_path(file_path_str: str, inbox_dir: Path, file_name: str) -> Path | None:
    """Try to locate the actual photo file on disk."""
    direct = Path(file_path_str)
    if direct.exists():
        return direct
    inbox_path = inbox_dir / file_name
    if inbox_path.exists():
        return inbox_path
    return None


def _thumb_bytes(image_path: Path, max_side: int = 400) -> bytes:
    """Load an image and return JPEG thumbnail bytes."""
    with Image.open(image_path) as img:
        img = img.convert("RGB")
        img.thumbnail((max_side, max_side), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        return buf.getvalue()


# ---------------------------------------------------------------------------
# HTML Templates
# ---------------------------------------------------------------------------

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, 'Segoe UI', Arial, sans-serif; background: #f0f2f5; color: #1a1a1a; padding-top: 56px; }

/* Sticky Navigation */
.navbar { position: fixed; top: 0; left: 0; right: 0; z-index: 900; background: #1a1a2e; color: #fff;
          height: 56px; display: flex; align-items: center; padding: 0 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.2); }
.navbar .brand { font-size: 18px; font-weight: 700; margin-right: 32px; color: #fff; text-decoration: none; }
.navbar .nav-links { display: flex; gap: 4px; }
.navbar .nav-links a { color: rgba(255,255,255,0.7); text-decoration: none; padding: 8px 16px; border-radius: 6px;
                       font-size: 14px; font-weight: 500; transition: all 0.15s; }
.navbar .nav-links a:hover { color: #fff; background: rgba(255,255,255,0.1); }
.navbar .nav-links a.active { color: #fff; background: rgba(255,255,255,0.15); }
.navbar .nav-right { margin-left: auto; font-size: 13px; opacity: 0.7; }

.header { background: #f0f2f5; color: #1a1a1a; padding: 16px 24px; display: flex; align-items: center; justify-content: space-between; }
.header h1 { font-size: 20px; font-weight: 600; }
.header .stats { font-size: 14px; color: #666; }
.container { max-width: 1200px; margin: 0 auto; padding: 20px; }
.breadcrumb { margin-bottom: 16px; font-size: 14px; }
.breadcrumb a { color: #4a6fa5; text-decoration: none; }
.breadcrumb a:hover { text-decoration: underline; }

/* Series list */
.series-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }
.series-card { background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); transition: transform 0.15s; }
.series-card:hover { transform: translateY(-2px); box-shadow: 0 4px 16px rgba(0,0,0,0.12); }
.series-card a { text-decoration: none; color: inherit; display: block; }
.series-thumb { width: 100%; height: 200px; object-fit: cover; background: #e0e0e0; }
.series-info { padding: 12px 16px; }
.series-name { font-size: 18px; font-weight: 600; margin-bottom: 4px; }
.series-meta { font-size: 13px; color: #666; }
.badge { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; color: #fff; }
.badge-selected { background: #2ecc71; }
.badge-empty { background: #e74c3c; }
.badge-rejected { background: #f39c12; }
.score-big { font-size: 22px; font-weight: 700; color: #2ecc71; float: right; margin-top: -4px; }
.score-zero { color: #ccc; }

/* Series detail & Nearby */
.photo-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.photo-card { background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); position: relative; }
.photo-card img.photo-thumb { width: 100%; height: 220px; object-fit: cover; cursor: pointer; }
.photo-card img.photo-thumb:hover { opacity: 0.9; }
.photo-info { padding: 12px 16px; }
.photo-name { font-size: 13px; color: #888; word-break: break-all; margin-bottom: 6px; }
.photo-score { font-size: 16px; font-weight: 600; margin-bottom: 8px; }
.rescue-btn { display: inline-block; background: #3498db; color: #fff; border: none; padding: 8px 20px;
              border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; text-decoration: none; }
.rescue-btn:hover { background: #2980b9; }
.rescue-btn.done { background: #2ecc71; cursor: default; }
.fullscreen-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
                      background: rgba(0,0,0,0.9); z-index: 1000; cursor: pointer; justify-content: center; align-items: center; }
.fullscreen-overlay.active { display: flex; }
.fullscreen-overlay img { max-width: 95%; max-height: 95%; object-fit: contain; }
.rescued-badge { display: inline-block; background: #2ecc71; color: #fff; padding: 2px 10px; border-radius: 12px; font-size: 12px; margin-left: 8px; }

/* Nearby browser */
.nearby-btn { display: inline-block; background: #4a6fa5; color: #fff; border: none; padding: 8px 20px;
              border-radius: 8px; font-size: 14px; font-weight: 700; cursor: pointer; text-decoration: none; margin-left: 8px;
              letter-spacing: 0.3px; }
.nearby-btn:hover { background: #3d5d8c; }
.series-divider { background: #f8f9fa; padding: 12px 20px; margin: 24px 0 16px; border-left: 4px solid #4a6fa5;
                  font-size: 16px; font-weight: 600; display: flex; align-items: center; justify-content: space-between; }
.series-divider.current { border-left-color: #e74c3c; background: #fef2f2; }
.batch-bar { position: sticky; bottom: 0; background: #1a1a2e; color: #fff; padding: 12px 24px;
             display: flex; align-items: center; justify-content: space-between; border-radius: 12px 12px 0 0;
             box-shadow: 0 -4px 16px rgba(0,0,0,0.2); z-index: 100; margin-top: 24px; }
.batch-bar .count { font-size: 16px; font-weight: 600; }
.batch-bar button { background: #2ecc71; color: #fff; border: none; padding: 10px 28px; border-radius: 8px;
                    font-size: 15px; font-weight: 700; cursor: pointer; }
.batch-bar button:hover { background: #27ae60; }
.batch-bar button:disabled { background: #555; cursor: default; }
.photo-checkbox { position: absolute; top: 8px; right: 8px; width: 24px; height: 24px; cursor: pointer;
                  accent-color: #2ecc71; z-index: 10; }
.photo-card.checked { outline: 3px solid #2ecc71; outline-offset: -3px; }

/* Settings page */
.settings-page { max-width: 900px; margin: 0 auto; }
.settings-group { background: #fff; border-radius: 12px; padding: 20px 24px; margin-bottom: 20px;
                  box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.settings-group h3 { font-size: 16px; font-weight: 600; margin-bottom: 4px; color: #1a1a2e; }
.settings-group .group-desc { font-size: 13px; color: #666; margin-bottom: 16px; }
.setting-row { display: flex; align-items: center; padding: 10px 0; border-bottom: 1px solid #f0f2f5; gap: 16px; }
.setting-row:last-child { border-bottom: none; }
.setting-label { flex: 0 0 280px; }
.setting-label .name { font-size: 14px; font-weight: 500; }
.setting-label .hint { font-size: 12px; color: #888; margin-top: 2px; }
.setting-control { flex: 1; display: flex; align-items: center; gap: 8px; }
.setting-control input[type=range] { flex: 1; max-width: 260px; accent-color: #4a6fa5; }
.setting-control input[type=number] { width: 80px; padding: 6px 8px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px; }
.setting-control input[type=text] { flex: 1; max-width: 400px; padding: 6px 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px; }
.setting-control select { padding: 6px 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px; }
.setting-control .val-display { min-width: 50px; text-align: right; font-size: 14px; font-weight: 600; color: #4a6fa5; }
.setting-control input[type=checkbox] { width: 20px; height: 20px; accent-color: #2ecc71; }
.save-bar { position: sticky; bottom: 0; background: #fff; padding: 16px 24px; border-top: 2px solid #4a6fa5;
            display: flex; align-items: center; justify-content: space-between; border-radius: 0 0 12px 12px;
            box-shadow: 0 -2px 8px rgba(0,0,0,0.1); margin-top: 8px; }
.save-bar button { background: #4a6fa5; color: #fff; border: none; padding: 10px 32px; border-radius: 8px;
                   font-size: 15px; font-weight: 600; cursor: pointer; }
.save-bar button:hover { background: #3d5d8c; }
.save-msg { font-size: 14px; color: #2ecc71; font-weight: 600; display: none; }
.save-msg.visible { display: inline; }

/* Auth modal */
.auth-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5);
               z-index: 2000; display: flex; justify-content: center; align-items: center; }
.auth-modal { background: #fff; border-radius: 16px; padding: 32px; width: 400px; max-width: 90%;
             box-shadow: 0 8px 32px rgba(0,0,0,0.3); position: relative; }
.auth-close { position: absolute; top: 12px; right: 16px; font-size: 28px; color: #999;
              text-decoration: none; line-height: 1; }
.auth-close:hover { color: #333; }
.auth-modal h2 { font-size: 20px; margin-bottom: 8px; }
.auth-modal .auth-hint { font-size: 14px; color: #666; margin-bottom: 20px; }
.auth-modal input[type=password] { width: 100%; padding: 12px 16px; border: 2px solid #ddd; border-radius: 8px;
                                   font-size: 16px; margin-bottom: 12px; transition: border-color 0.2s; }
.auth-modal input[type=password]:focus { border-color: #4a6fa5; outline: none; }
.auth-modal .auth-btn { width: 100%; background: #4a6fa5; color: #fff; border: none; padding: 12px;
                        border-radius: 8px; font-size: 16px; font-weight: 600; cursor: pointer; }
.auth-modal .auth-btn:hover { background: #3d5d8c; }
.auth-modal .auth-error { color: #e74c3c; font-size: 14px; font-weight: 600; margin-top: 8px; display: none; }
.auth-modal .auth-error.visible { display: block; }

/* Change password section */
.change-pw-section { background: #f8f9fa; border-radius: 12px; padding: 20px 24px; margin-top: 20px; }
.change-pw-section h3 { font-size: 16px; font-weight: 600; margin-bottom: 12px; }
.change-pw-section input[type=password] { width: 100%; max-width: 300px; padding: 8px 12px; border: 1px solid #ddd;
                                          border-radius: 6px; font-size: 14px; margin-bottom: 8px; display: block; }
.change-pw-section button { background: #e74c3c; color: #fff; border: none; padding: 8px 20px; border-radius: 6px;
                            font-size: 14px; font-weight: 600; cursor: pointer; margin-top: 4px; }
.change-pw-section button:hover { background: #c0392b; }
.change-pw-msg { font-size: 13px; margin-top: 8px; }

/* Pagination controls */
.pagination-bar { display: flex; align-items: center; justify-content: center; gap: 8px; margin: 24px 0 16px;
                  flex-wrap: wrap; }
.pagination-bar .page-btn { background: #fff; color: #1a1a2e; border: 1px solid #ddd; padding: 8px 16px;
                            border-radius: 8px; font-size: 14px; font-weight: 500; cursor: pointer;
                            text-decoration: none; transition: all 0.15s; }
.pagination-bar .page-btn:hover { background: #4a6fa5; color: #fff; border-color: #4a6fa5; }
.pagination-bar .page-btn.active { background: #4a6fa5; color: #fff; border-color: #4a6fa5; }
.pagination-bar .page-btn.load-more { background: #1a1a2e; color: #fff; border-color: #1a1a2e; padding: 8px 24px; }
.pagination-bar .page-btn.load-more:hover { background: #2a2a4e; }
.pagination-info { text-align: center; font-size: 13px; color: #888; margin-bottom: 8px; }

/* Card size switcher */
.view-switcher { display: flex; gap: 4px; margin-left: 16px; }
.view-switcher button { background: rgba(255,255,255,0.1); border: none; color: rgba(255,255,255,0.6);
                        padding: 6px 10px; border-radius: 6px; cursor: pointer; font-size: 13px; }
.view-switcher button:hover { background: rgba(255,255,255,0.2); color: #fff; }
.view-switcher button.active { background: rgba(255,255,255,0.2); color: #fff; }
.series-grid.view-large { grid-template-columns: repeat(auto-fill, minmax(420px, 1fr)); }
.series-grid.view-large .series-thumb { height: 280px; }
.series-grid.view-medium { grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); }
.series-grid.view-medium .series-thumb { height: 200px; }
.series-grid.view-small { grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); }
.series-grid.view-small .series-thumb { height: 130px; }
.series-grid.view-small .series-name { font-size: 14px; }
.series-grid.view-small .series-meta { font-size: 12px; }
.series-grid.view-small .score-big { font-size: 16px; }
"""

_JS = r"""
function showFull(src, evt) {
    if (evt && evt.target.type === 'checkbox') return;
    var ov = document.getElementById('fullscreen');
    ov.querySelector('img').src = src.replace('max_side=400', 'max_side=1600');
    ov.classList.add('active');
}
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') document.getElementById('fullscreen').classList.remove('active');
});

function updateBatchCount() {
    var checked = document.querySelectorAll('.photo-checkbox:checked');
    var countEl = document.getElementById('batch-count');
    var btn = document.getElementById('batch-send');
    if (countEl) {
        countEl.textContent = String(checked.length);
        btn.disabled = checked.length === 0;
    }
}
function toggleCard(cb) {
    var card = cb.closest('.photo-card');
    if (cb.checked) card.classList.add('checked');
    else card.classList.remove('checked');
    updateBatchCount();
}
function selectAll() {
    var cbs = document.querySelectorAll('.photo-checkbox');
    for (var i = 0; i < cbs.length; i++) {
        cbs[i].checked = true;
        cbs[i].closest('.photo-card').classList.add('checked');
    }
    updateBatchCount();
}
function selectNone() {
    var cbs = document.querySelectorAll('.photo-checkbox');
    for (var i = 0; i < cbs.length; i++) {
        cbs[i].checked = false;
        cbs[i].closest('.photo-card').classList.remove('checked');
    }
    updateBatchCount();
}
function confirmRescue(formId, fileName) {
    if (confirm('Скопировать фото ' + fileName + ' в папку selected?')) {
        document.getElementById(formId).submit();
    }
}
// Auth
function authLogin() {
    var pwd = document.getElementById('auth-password');
    if (!pwd) return;
    var errEl = document.getElementById('auth-error');
    fetch('/api/auth', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({password: pwd.value}),
        credentials: 'same-origin'
    }).then(function(resp) {
        if (resp.ok) {
            return resp.json().then(function(data) {
                if (data.first_login) {
                    location.href = '/settings#change-password';
                } else {
                    location.reload();
                }
            });
        } else {
            if (errEl) { errEl.textContent = 'Неверный пароль'; errEl.className = 'auth-error visible'; }
            pwd.value = '';
            pwd.focus();
        }
    }).catch(function(e) {
        if (errEl) { errEl.textContent = 'Ошибка соединения: ' + e.message; errEl.className = 'auth-error visible'; }
    });
}
function authKeydown(e) { if (e.key === 'Enter') authLogin(); }

// Change password
function changePassword() {
    var cur = document.getElementById('pw-current').value;
    var nw = document.getElementById('pw-new').value;
    var conf = document.getElementById('pw-confirm').value;
    var msg = document.getElementById('pw-msg');
    if (!cur || !nw) { msg.textContent = 'Заполните все поля'; msg.style.color = '#e74c3c'; return; }
    if (nw !== conf) { msg.textContent = 'Пароли не совпадают'; msg.style.color = '#e74c3c'; return; }
    if (nw.length < 4) { msg.textContent = 'Минимум 4 символа'; msg.style.color = '#e74c3c'; return; }
    fetch('/api/change-password', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({current: cur, new_password: nw}),
        credentials: 'same-origin'
    }).then(function(resp) {
        if (resp.ok) {
            msg.textContent = 'Пароль изменён!'; msg.style.color = '#2ecc71';
            document.getElementById('pw-current').value = '';
            document.getElementById('pw-new').value = '';
            document.getElementById('pw-confirm').value = '';
        } else {
            msg.textContent = 'Неверный текущий пароль'; msg.style.color = '#e74c3c';
        }
    }).catch(function(e) {
        msg.textContent = 'Ошибка: ' + e.message; msg.style.color = '#e74c3c';
    });
}

// Monitor control
function toggleMonitor(action) {
    fetch('/api/monitor', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action: action}),
        credentials: 'same-origin'
    }).then(function() { location.reload(); })
    .catch(function(e) { alert('Ошибка: ' + e.message); });
}

// View switcher
function setView(mode) {
    var grid = document.querySelector('.series-grid');
    if (!grid) return;
    grid.className = 'series-grid view-' + mode;
    var btns = document.querySelectorAll('.view-switcher button');
    for (var i = 0; i < btns.length; i++) {
        btns[i].className = btns[i].getAttribute('data-view') === mode ? 'active' : '';
    }
    localStorage.setItem('kanatka_view', mode);
}
// Restore view preference on load
(function() {
    var saved = localStorage.getItem('kanatka_view');
    if (saved) {
        document.addEventListener('DOMContentLoaded', function() { setView(saved); });
    }
})();

function confirmAmbiguous(seriesName) {
    if (!confirm('Подтвердить выбор для серии ' + seriesName + '? Фото будет перемещено в selected и станет доступно для следующего листа.')) return;
    fetch('/api/confirm-ambiguous', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({series: seriesName}),
        credentials: 'same-origin'
    }).then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.ok) { location.reload(); }
        else { alert('Ошибка: ' + (data.error || 'неизвестная')); }
    })
    .catch(function(e) { alert('Ошибка: ' + e.message); });
}

function submitBatch() {
    var checked = document.querySelectorAll('.photo-checkbox:checked');
    if (checked.length === 0) return;
    if (!confirm('Отправить на печать ' + checked.length + ' фото? Они будут скопированы в selected и синхронизированы в сетевую папку.')) return;
    var form = document.getElementById('batch-form');
    var container = document.getElementById('batch-inputs');
    // Clear previous hidden inputs
    while (container.firstChild) container.removeChild(container.firstChild);
    // Add count
    var countInp = document.createElement('input');
    countInp.type = 'hidden'; countInp.name = 'count'; countInp.value = String(checked.length);
    container.appendChild(countInp);
    // Add each photo
    for (var i = 0; i < checked.length; i++) {
        var cb = checked[i];
        var inp1 = document.createElement('input');
        inp1.type = 'hidden'; inp1.name = 'path_' + i; inp1.value = cb.getAttribute('data-path');
        container.appendChild(inp1);
        var inp2 = document.createElement('input');
        inp2.type = 'hidden'; inp2.name = 'series_' + i; inp2.value = cb.getAttribute('data-series');
        container.appendChild(inp2);
    }
    form.submit();
}

// Cleanup modal
function openCleanup() {
    document.getElementById('cleanup-modal').style.display = 'flex';
}
function closeCleanup() {
    document.getElementById('cleanup-modal').style.display = 'none';
}
function toggleCleanupAll(master) {
    var cbs = document.querySelectorAll('#cleanup-modal input[type=checkbox][name]');
    for (var i = 0; i < cbs.length; i++) cbs[i].checked = master.checked;
}
function runCleanup() {
    var cbs = document.querySelectorAll('#cleanup-modal input[type=checkbox][name]:checked');
    if (cbs.length === 0) { alert('Ничего не выбрано'); return; }
    var folders = [];
    for (var i = 0; i < cbs.length; i++) folders.push(cbs[i].name);
    var names = [];
    for (var i = 0; i < cbs.length; i++) names.push(cbs[i].parentElement.textContent.trim());
    fetch('/api/cleanup', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({folders: folders}),
        credentials: 'same-origin'
    }).then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.status === 'ok') {
            closeCleanup();
            location.reload();
        } else {
            alert('Ошибка: ' + (data.error || 'неизвестная'));
        }
    })
    .catch(function(e) { alert('Ошибка: ' + e.message); });
}

function openFullscreen(src) {
    var ov = document.getElementById('fullscreen');
    ov.querySelector('img').src = src;
    ov.classList.add('active');
}
"""


def _page(title: str, body: str, stats: str = "", active_nav: str = "series",
          show_view_switcher: bool = False) -> str:
    def nav_cls(name: str) -> str:
        return "active" if name == active_nav else ""

    view_switcher_html = ""
    if show_view_switcher:
        view_switcher_html = (
            '<div class="view-switcher">'
            '<button data-view="large" onclick="setView(\'large\')" title="Крупные">&#9634;</button>'
            '<button data-view="medium" class="active" onclick="setView(\'medium\')" title="Средние">&#9635;</button>'
            '<button data-view="small" onclick="setView(\'small\')" title="Мелкие">&#9636;</button>'
            '</div>'
        )

    # Monitor status indicator
    mon = _MonitorState.status_dict()
    if mon["active"]:
        monitor_html = (
            '<span style="margin-left:16px; font-size:13px; color:#2ecc71; font-weight:600">'
            '&#9679; Мониторинг'
            '</span>'
        )
    else:
        monitor_html = ""

    # Ambiguous series indicator
    ambiguous_count = _count_ambiguous_series()
    if ambiguous_count > 0:
        monitor_html += (
            f'<a href="/?filter=ambiguous" style="margin-left:12px; font-size:13px; '
            f'color:#f39c12; font-weight:600; text-decoration:none">'
            f'&#9888; {ambiguous_count} спорных'
            f'</a>'
        )

    # Test mode / autoprint indicator
    _cfg = getattr(SeriesBrowserHandler, "config", None) or {}
    _print_cfg = _cfg.get("print", {})
    if _print_cfg.get("test_mode", False):
        monitor_html += (
            '<span style="margin-left:12px; font-size:13px; color:#f1c40f; '
            'font-weight:700; background:#333; padding:2px 8px; border-radius:6px">'
            'TEST MODE</span>'
        )
    elif _print_cfg.get("autoprint", False):
        monitor_html += (
            '<span style="margin-left:12px; font-size:13px; color:#2ecc71; font-weight:600">'
            '&#9113; Автопечать</span>'
        )

    return (
        '<!DOCTYPE html>\n'
        '<html lang="ru"><head>\n'
        '<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{title}</title>\n'
        f'<style>{_CSS}</style>\n'
        '</head><body>\n'
        '<nav class="navbar">\n'
        '  <a href="/" class="brand">&#127935; Kanatka</a>\n'
        '  <div class="nav-links">\n'
        f'    <a href="/" class="{nav_cls("series")}">Серии</a>\n'
        f'    <a href="/sheets" class="{nav_cls("sheets")}">&#128196; Листы</a>\n'
        f'    <a href="/settings" class="{nav_cls("settings")}">&#9881; Настройки</a>\n'
        '    <a href="#" onclick="openCleanup(); return false;" style="color:#e74c3c">&#128465; Очистка</a>\n'
        '  </div>\n'
        f'  {view_switcher_html}'
        f'  {monitor_html}'
        f'  <div class="nav-right">{stats}</div>\n'
        '</nav>\n'
        f'<div class="container">{body}</div>\n'
        '<div id="cleanup-modal" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%;'
        ' background:rgba(0,0,0,0.5); z-index:9999; align-items:center; justify-content:center">'
        '<div style="background:#fff; border-radius:16px; padding:28px 32px; max-width:420px; width:90%">'
        '<h3 style="margin-top:0">&#128465; Очистка рабочих папок</h3>'
        '<p style="color:#666; font-size:13px; margin-bottom:16px">Выберите папки для очистки. Файлы будут удалены безвозвратно.</p>'
        '<div style="display:flex; flex-direction:column; gap:10px">'
        '<label style="cursor:pointer"><input type="checkbox" name="incoming"> Входящие фото (ожидают обработки)</label>'
        '<label style="cursor:pointer"><input type="checkbox" name="selected"> Лучшие фото (отобранные)</label>'
        '<label style="cursor:pointer"><input type="checkbox" name="rejected"> Худшие фото серий</label>'
        '<label style="cursor:pointer"><input type="checkbox" name="discarded"> Пустые кресла</label>'
        '<label style="cursor:pointer"><input type="checkbox" name="ambiguous"> Спорные серии</label>'
        '<label style="cursor:pointer"><input type="checkbox" name="sheets"> Печатные листы</label>'
        '<label style="cursor:pointer"><input type="checkbox" name="archive"> Архив обработанных</label>'
        '<label style="cursor:pointer"><input type="checkbox" name="logs"> Отчёты серий, логи, аннотации</label>'
        '<hr style="margin:8px 0">'
        '<label style="cursor:pointer; color:#e74c3c; font-weight:700"><input type="checkbox" onchange="toggleCleanupAll(this)"> Выбрать всё</label>'
        '</div>'
        '<div style="display:flex; gap:12px; margin-top:20px; justify-content:flex-end">'
        '<button onclick="closeCleanup()" style="padding:8px 20px; border:1px solid #ddd; border-radius:8px; background:#fff; cursor:pointer">Отмена</button>'
        '<button onclick="runCleanup()" style="padding:8px 20px; border:none; border-radius:8px; background:#e74c3c; color:#fff; cursor:pointer; font-weight:600">Удалить</button>'
        '</div></div></div>\n'
        '<div id="fullscreen" class="fullscreen-overlay" onclick="this.classList.remove(\'active\')"><img src=""></div>\n'
        f'<script>{_JS}</script>\n'
        '</body></html>'
    )


def _score_to_stars(score_val: float) -> tuple[int, str]:
    """Convert 0-100 score to 1-5 stars and a label."""
    if score_val >= 85:
        return 5, "Отлично"
    if score_val >= 65:
        return 4, "Хорошо"
    if score_val >= 45:
        return 3, "Средне"
    if score_val >= 25:
        return 2, "Слабо"
    if score_val > 0:
        return 1, "Плохо"
    return 0, "Нет данных"


def _score_span(score_val: float) -> str:
    color = "#2ecc71" if score_val >= 80 else "#f39c12" if score_val >= 40 else "#e74c3c"
    stars, label = _score_to_stars(score_val)
    star_html = '<span style="color:#f1c40f; letter-spacing:1px">' + "&#9733;" * stars + "&#9734;" * (5 - stars) + '</span>'
    return (
        f'<span style="color:{color}; font-weight:700">{score_val:.1f}</span> '
        f'{star_html} '
        f'<span style="color:#888; font-size:12px">{label}</span>'
    )


def _detect_label(present: bool, fallback: bool) -> str:
    if present and fallback:
        return "Силуэт (без лица)"
    if present:
        return "Лицо найдено"
    return "Не обнаружен"


_SERIES_PER_PAGE = 20


def _render_series_card(series: dict) -> str:
    """Render a single series card HTML."""
    name = series.get("series", "?")
    status = series.get("status", "unknown")
    score = series.get("best_score", 0)
    photos = series.get("photos", [])
    photo_count = len(photos)

    if status == "selected":
        badge = '<span class="badge badge-selected">Выбрано</span>'
    elif status == "ambiguous_manual_review":
        badge = '<span class="badge" style="background:#f39c12; color:#fff">&#9888; Спорная</span>'
    elif status == "discarded_empty":
        badge = '<span class="badge badge-empty">Пустое</span>'
    else:
        badge = '<span class="badge badge-rejected">Отклонено</span>'

    score_val = score if isinstance(score, (int, float)) else 0
    score_cls = "score-big" if score_val > 0 else "score-big score-zero"
    score_html = f'<span class="{score_cls}">{score_val:.0f}</span>' if score_val else ""

    thumb_src = ""
    if photos:
        first_path = photos[0].get("file_path", "")
        thumb_src = f'/photo?path={quote(first_path, safe="")}&amp;max_side=400'

    return (
        '<div class="series-card">'
        f'<a href="/series/{name}">'
        f'<img class="series-thumb" src="{thumb_src}" alt="{name}" loading="lazy"'
        " onerror=\"this.style.display='none'\">"
        '<div class="series-info">'
        f'<div class="series-name">{name} {score_html}</div>'
        f'<div class="series-meta">{badge} &middot; {photo_count} фото</div>'
        '</div></a>'
        f'<div style="padding:0 16px 12px; display:flex; gap:6px">'
        f'<a href="/nearby/{name}" class="nearby-btn" style="font-size:12px; padding:5px 12px">'
        'Рядом</a>'
        + (f'<button onclick="confirmAmbiguous(\'{name}\')" class="nearby-btn" '
           f'style="font-size:12px; padding:5px 12px; background:#27ae60; color:#fff; border:none; cursor:pointer">'
           f'Подтвердить</button>'
           if status == "ambiguous_manual_review" else "")
        + '</div>'
        '</div>'
    )


def _render_series_list(all_series: list[dict], page: int = 1, filter_status: str = "") -> str:
    selected_count = sum(1 for s in all_series if s.get("status") == "selected")
    empty_count = sum(1 for s in all_series if s.get("status") == "discarded_empty")
    ambiguous_count = sum(1 for s in all_series if s.get("status") == "ambiguous_manual_review")
    total = len(all_series)
    stats = f"Всего: {total} | Выбрано: {selected_count} | Спорных: {ambiguous_count} | Пустых: {empty_count}"

    # Filter
    if filter_status == "ambiguous":
        display_series = [s for s in all_series if s.get("status") == "ambiguous_manual_review"]
    else:
        display_series = all_series

    # Pagination
    filtered_total = len(display_series)
    total_pages = max(1, (filtered_total + _SERIES_PER_PAGE - 1) // _SERIES_PER_PAGE)
    page = max(1, min(page, total_pages))
    start = (page - 1) * _SERIES_PER_PAGE
    end = min(start + _SERIES_PER_PAGE, filtered_total)
    page_series = display_series[start:end]

    cards = [_render_series_card(s) for s in page_series]

    # Filter tabs
    filter_param = f"&filter={filter_status}" if filter_status else ""
    all_cls = "" if filter_status else "active"
    amb_cls = "active" if filter_status == "ambiguous" else ""
    filter_tabs = (
        '<div style="margin-bottom:12px; display:flex; gap:8px">'
        f'<a href="/" class="page-btn {all_cls}" style="text-decoration:none">Все ({total})</a>'
        f'<a href="/?filter=ambiguous" class="page-btn {amb_cls}" style="text-decoration:none; '
        f'color:{("#f39c12" if ambiguous_count else "#999")}">'
        f'&#9888; Спорные ({ambiguous_count})</a>'
        '</div>'
    )

    # Pagination controls
    pagination = ""
    if total_pages > 1:
        parts = []
        parts.append(f'<div class="pagination-info">Стр. {page} из {total_pages} ({filtered_total} серий)</div>')
        parts.append('<div class="pagination-bar">')

        if page > 1:
            parts.append(f'<a href="/?page={page - 1}{filter_param}" class="page-btn">&larr; Назад</a>')

        # Show up to 7 page buttons
        start_p = max(1, page - 3)
        end_p = min(total_pages, start_p + 6)
        start_p = max(1, end_p - 6)

        for p in range(start_p, end_p + 1):
            cls = "page-btn active" if p == page else "page-btn"
            parts.append(f'<a href="/?page={p}{filter_param}" class="{cls}">{p}</a>')

        if page < total_pages:
            parts.append(f'<a href="/?page={page + 1}{filter_param}" class="page-btn">Далее &rarr;</a>')
            parts.append(f'<a href="/?page={page + 1}{filter_param}" class="page-btn load-more">Загрузить ещё</a>')

        parts.append('</div>')
        pagination = "\n".join(parts)

    # Monitor control bar
    mon = _MonitorState.status_dict()
    if mon["active"]:
        monitor_bar = (
            '<div style="background:#e8f5e9; border-radius:12px; padding:16px 20px; margin-bottom:16px; '
            'display:flex; align-items:center; justify-content:space-between; border:1px solid #a5d6a7">'
            '<div>'
            '<span style="color:#2e7d32; font-weight:700; font-size:15px">&#9679; Мониторинг активен</span>'
            f'<span style="color:#666; font-size:13px; margin-left:12px">Обработано серий: {mon["series_processed"]}</span>'
            + (f'<span style="color:#888; font-size:13px; margin-left:12px">Последнее: {mon["last_activity"]}</span>'
               if mon["last_activity"] else "")
            + '</div>'
            '<button onclick="toggleMonitor(\'stop\')" style="background:#e74c3c; color:#fff; border:none; '
            'padding:8px 20px; border-radius:8px; font-size:14px; font-weight:600; cursor:pointer">Остановить</button>'
            '</div>'
        )
    else:
        err_html = (f'<span style="color:#e74c3c; font-size:13px; margin-left:12px">{mon["error"]}</span>'
                    if mon["error"] else "")
        monitor_bar = (
            '<div style="background:#fff; border-radius:12px; padding:16px 20px; margin-bottom:16px; '
            'display:flex; align-items:center; justify-content:space-between; box-shadow:0 2px 8px rgba(0,0,0,0.06)">'
            '<div>'
            '<span style="color:#666; font-size:14px">&#128247; Автономный режим: мониторинг входящих фото</span>'
            + err_html
            + '</div>'
            '<button onclick="toggleMonitor(\'start\')" style="background:#2ecc71; color:#fff; border:none; '
            'padding:8px 20px; border-radius:8px; font-size:14px; font-weight:600; cursor:pointer">Запустить</button>'
            '</div>'
        )

    body = (
        monitor_bar
        + filter_tabs
        + '<div class="series-grid view-medium">'
        + "".join(cards)
        + '</div>'
        + pagination
    )
    return _page("Kanatka — Серии", body, stats, show_view_switcher=True)


def _render_series_detail(series: dict, selected_dir: Path) -> str:
    name = series.get("series", "?")
    photos = series.get("photos", [])
    selected_file = series.get("selected_file", "")
    existing_selected = {p.name for p in selected_dir.glob("*.jpg")}

    breadcrumb = (
        '<div class="breadcrumb">'
        '<a href="/">&larr; Все серии</a> / ' + name
        + f' <a href="/nearby/{name}" class="nearby-btn">Посмотреть рядом</a>'
        + '</div>'
    )

    cards = []
    for photo in photos:
        fname = photo.get("file_name", "?")
        fpath = photo.get("file_path", "")
        score = photo.get("score", 0)
        present = photo.get("subject_present", False)
        fallback = photo.get("person_fallback", False)

        thumb_src = f'/photo?path={quote(fpath, safe="")}&amp;max_side=400'
        full_src = f'/photo?path={quote(fpath, safe="")}&amp;max_side=1600'

        score_val = score if isinstance(score, (int, float)) else 0
        detect_info = _detect_label(present, fallback)

        rescue_name = f"{name}_{fname}"
        already_rescued = rescue_name in existing_selected or selected_file == rescue_name
        if already_rescued:
            rescue_html = '<span class="rescued-badge">Уже выбрано</span>'
        else:
            form_id = f"rescue_{fname.replace('.', '_')}"
            rescue_html = (
                f'<form id="{form_id}" method="POST" action="/rescue" style="display:inline">'
                f'<input type="hidden" name="path" value="{fpath}">'
                f'<input type="hidden" name="series" value="{name}">'
                f'<input type="hidden" name="file_name" value="{fname}">'
                f'<button type="button" class="rescue-btn" onclick="confirmRescue(\'{form_id}\', \'{fname}\')">Спасти фото</button>'
                '</form>'
            )

        cards.append(
            '<div class="photo-card">'
            f'<img class="photo-thumb" src="{thumb_src}" alt="{fname}" loading="lazy"'
            f" onclick=\"showFull('{full_src}', event)\""
            " onerror=\"this.style.display='none'\">"
            '<div class="photo-info">'
            f'<div class="photo-name">{fname}</div>'
            f'<div class="photo-score">Score: {_score_span(score_val)} &middot; {detect_info}</div>'
            f'{rescue_html}'
            '</div></div>'
        )

    body = breadcrumb + f'<h2 style="margin-bottom:16px">{name} — {len(photos)} фото</h2>'
    body += '<div class="photo-grid">' + "".join(cards) + '</div>'
    return _page(f"Kanatka — {name}", body)


def _render_nearby(
    center_series: dict,
    all_series: list[dict],
    selected_dir: Path,
    radius: int = 3,
) -> str:
    """Render the temporal browser showing photos from neighboring series.

    Shows ``radius`` series before and after the center series, with
    checkboxes for batch selection and a sticky action bar at the bottom.
    """
    center_name = center_series.get("series", "?")
    existing_selected = {p.name for p in selected_dir.glob("*.jpg")}

    # Find index of center series
    center_idx = None
    for i, s in enumerate(all_series):
        if s.get("series") == center_name:
            center_idx = i
            break
    if center_idx is None:
        return _page("Ошибка", f"<h2>Серия {center_name} не найдена</h2>")

    # Get neighboring series
    start = max(0, center_idx - radius)
    end = min(len(all_series), center_idx + radius + 1)
    nearby = all_series[start:end]

    total_photos = sum(len(s.get("photos", [])) for s in nearby)
    stats = f"{len(nearby)} серий ({total_photos} фото) вокруг {center_name}"

    breadcrumb = (
        '<div class="breadcrumb">'
        '<a href="/">&larr; Все серии</a> / '
        f'<a href="/series/{center_name}">{center_name}</a> / '
        'Соседние серии</div>'
    )

    body_parts = [breadcrumb]
    body_parts.append(
        f'<h2 style="margin-bottom:8px">Серии рядом с {center_name}</h2>'
        '<p style="color:#666; margin-bottom:16px; font-size:14px">'
        'Выберите нужные фото галочками и нажмите &laquo;Отправить на печать&raquo; внизу. '
        'Выбранные фото будут скопированы в папку selected и синхронизированы в сетевую папку.</p>'
        '<div style="margin-bottom:16px">'
        '<button onclick="selectAll()" class="rescue-btn" style="font-size:12px; padding:4px 12px">Выбрать все</button> '
        '<button onclick="selectNone()" class="rescue-btn" style="font-size:12px; padding:4px 12px; background:#95a5a6">Снять все</button>'
        '</div>'
    )

    for series in nearby:
        name = series.get("series", "?")
        status = series.get("status", "unknown")
        photos = series.get("photos", [])
        is_center = name == center_name

        if status == "selected":
            badge_html = '<span class="badge badge-selected">Выбрано</span>'
        elif status == "discarded_empty":
            badge_html = '<span class="badge badge-empty">Пустое</span>'
        else:
            badge_html = '<span class="badge badge-rejected">Отклонено</span>'

        divider_cls = "series-divider current" if is_center else "series-divider"
        center_marker = " (текущая)" if is_center else ""
        body_parts.append(
            f'<div class="{divider_cls}">'
            f'<span>{name}{center_marker} &mdash; {len(photos)} фото</span>'
            f'<span>{badge_html}</span>'
            '</div>'
        )

        cards = []
        for photo in photos:
            fname = photo.get("file_name", "?")
            fpath = photo.get("file_path", "")
            score = photo.get("score", 0)
            present = photo.get("subject_present", False)
            fallback = photo.get("person_fallback", False)

            thumb_src = f'/photo?path={quote(fpath, safe="")}&amp;max_side=400'
            full_src = f'/photo?path={quote(fpath, safe="")}&amp;max_side=1600'

            score_val = score if isinstance(score, (int, float)) else 0
            detect_info = _detect_label(present, fallback)

            rescue_name = f"{name}_{fname}"
            already = rescue_name in existing_selected
            already_html = ' <span class="rescued-badge">Уже</span>' if already else ""

            cards.append(
                '<div class="photo-card">'
                f'<input type="checkbox" class="photo-checkbox"'
                f' data-path="{fpath}" data-series="{name}"'
                ' onchange="toggleCard(this)">'
                f'<img class="photo-thumb" src="{thumb_src}" alt="{fname}" loading="lazy"'
                f" onclick=\"showFull('{full_src}', event)\""
                " onerror=\"this.style.display='none'\">"
                '<div class="photo-info">'
                f'<div class="photo-name">{fname}</div>'
                f'<div class="photo-score">Score: {_score_span(score_val)} &middot; {detect_info}{already_html}</div>'
                '</div></div>'
            )

        body_parts.append('<div class="photo-grid">' + "".join(cards) + '</div>')

    # Batch action bar
    body_parts.append(
        f'<form id="batch-form" method="POST" action="/rescue-batch">'
        f'<input type="hidden" name="redirect" value="/nearby/{center_name}">'
        '<div id="batch-inputs"></div>'
        '</form>'
        '<div class="batch-bar">'
        '<div class="count">Выбрано: <span id="batch-count">0</span> фото</div>'
        '<button id="batch-send" onclick="submitBatch()" disabled>'
        'Отправить на печать'
        '</button>'
        '</div>'
    )

    body = "\n".join(body_parts)
    return _page(f"Kanatka — рядом с {center_name}", body, stats)


# ---------------------------------------------------------------------------
# Settings page
# ---------------------------------------------------------------------------

# Each setting: (config_section, config_key, label, hint, input_type, extra)
# input_type: "range", "number", "checkbox", "text"
# extra: dict with min, max, step for range/number
_SETTINGS_SCHEMA: list[tuple[str, str, list[tuple]]] = [
    (
        "Детекция серий",
        "Как программа группирует кадры в серии по времени съёмки.",
        [
            ("series_detection", "max_gap_seconds", "Макс. пауза между кадрами",
             "Если между двумя кадрами прошло меньше этого времени — они в одной серии.",
             "range", {"min": 0.1, "max": 10, "step": 0.1}),
            ("series_detection", "cooldown_seconds", "Пауза между сериями",
             "Минимальное время между последним кадром одной серии и первым кадром следующей.",
             "range", {"min": 0.5, "max": 30, "step": 0.1}),
        ],
    ),
    (
        "Детекция людей (Haar cascade)",
        "Параметры fallback-детектора для людей без видимого лица (шлем, очки, ракурс).",
        [
            ("haar_cascade", "scale_factor", "Scale Factor",
             "Как сильно уменьшается изображение на каждом шаге. Меньше = точнее, но медленнее. 1.05 = хороший баланс.",
             "range", {"min": 1.01, "max": 1.30, "step": 0.01}),
            ("haar_cascade", "min_neighbors", "Min Neighbors",
             "Сколько соседних прямоугольников нужно для подтверждения. Больше = меньше ложных срабатываний, но можно пропустить.",
             "range", {"min": 1, "max": 10, "step": 1}),
            ("haar_cascade", "min_size", "Min Size (px)",
             "Минимальный размер объекта в пикселях. Меньше = ловит мелкие фигуры, но больше шума.",
             "range", {"min": 20, "max": 200, "step": 10}),
        ],
    ),
    (
        "Пороги скоринга",
        "Пороги для расчёта оценки качества кадра.",
        [
            ("thresholds", "min_face_confidence", "Мин. уверенность лица",
             "MediaPipe confidence ниже этого порога — лицо игнорируется.",
             "range", {"min": 0.1, "max": 1.0, "step": 0.05}),
            ("thresholds", "min_person_confidence", "Мин. уверенность человека",
             "Порог для Haar cascade fallback.",
             "range", {"min": 0.1, "max": 1.0, "step": 0.05}),
            ("thresholds", "min_head_sharpness", "Мин. резкость головы",
             "Laplacian variance ниже этого = размытое фото (0 баллов за резкость).",
             "range", {"min": 5, "max": 100, "step": 5}),
            ("thresholds", "good_head_sharpness", "Хорошая резкость головы",
             "Laplacian variance выше этого = максимальная оценка за резкость.",
             "range", {"min": 50, "max": 500, "step": 10}),
            ("thresholds", "min_frame_sharpness", "Мин. резкость кадра",
             "Для кадров без лица — нижняя граница Laplacian.",
             "range", {"min": 10, "max": 200, "step": 10}),
            ("thresholds", "good_frame_sharpness", "Хорошая резкость кадра",
             "Для кадров без лица — верхняя граница Laplacian.",
             "range", {"min": 100, "max": 800, "step": 10}),
            ("thresholds", "target_head_brightness", "Целевая яркость головы",
             "Оптимальная яркость зоны лица (0–255). 145 = нормальное дневное освещение.",
             "range", {"min": 50, "max": 220, "step": 5}),
            ("thresholds", "head_brightness_tolerance", "Допуск яркости",
             "Насколько яркость может отклоняться от цели и всё ещё считаться хорошей.",
             "range", {"min": 20, "max": 150, "step": 5}),
            ("thresholds", "fallback_score_ceiling", "Потолок fallback-кадра",
             "Макс. оценка для кадра без найденного лица (только силуэт). Защита от ложных побед fallback.",
             "range", {"min": 10, "max": 80, "step": 5}),
            ("thresholds", "quality_fail_sharpness", "Брак: резкость",
             "Резкость ниже этого порога = явный брак (экстремальный смаз).",
             "range", {"min": 5, "max": 50, "step": 5}),
            ("thresholds", "quality_weak_sharpness", "Слабая резкость",
             "Резкость ниже этого порога = ограниченная оценка (мягкий потолок).",
             "range", {"min": 15, "max": 80, "step": 5}),
            ("thresholds", "pose_yaw_tolerance", "Допуск поворота головы",
             "Макс. отклонение yaw (градусы) от фронтального ракурса. Больше = мягче к профилю.",
             "range", {"min": 15, "max": 90, "step": 5}),
        ],
    ),
    (
        "Веса скоринга",
        "Как распределяется вес между компонентами оценки (сумма = 100).",
        [
            ("scoring_weights", "head_readability", "Читаемость лица",
             "Вес компонента: насколько хорошо распознаётся лицо (уверенность + ракурс + резкость).",
             "range", {"min": 0, "max": 100, "step": 5}),
            ("scoring_weights", "head_pose", "Ракурс головы",
             "Вес компонента: предпочтение фронтальным ракурсам.",
             "range", {"min": 0, "max": 100, "step": 5}),
            ("scoring_weights", "head_sharpness", "Резкость лица",
             "Вес компонента: локальная резкость области лица.",
             "range", {"min": 0, "max": 100, "step": 5}),
            ("scoring_weights", "head_exposure", "Освещение лица",
             "Вес компонента: яркость области лица (ближе к целевой = лучше).",
             "range", {"min": 0, "max": 100, "step": 5}),
            ("scoring_weights", "readable_count", "Кол-во читаемых",
             "Вес компонента: бонус за несколько читаемых людей на кресле.",
             "range", {"min": 0, "max": 100, "step": 5}),
            ("scoring_weights", "frame_quality", "Качество кадра",
             "Вес компонента: общая резкость и яркость всего кадра.",
             "range", {"min": 0, "max": 100, "step": 5}),
            ("scoring_weights", "smile_bonus", "Бонус за улыбку",
             "Вес компонента: слабое предпочтение позитивному выражению. Не должен побеждать читаемость.",
             "range", {"min": 0, "max": 10, "step": 1}),
        ],
    ),
    (
        "Обработка",
        "Общие параметры обработки изображений.",
        [
            ("processing", "resize_longest_side", "Макс. сторона (px)",
             "Длинная сторона изображения уменьшается до этого размера для анализа.",
             "range", {"min": 640, "max": 3840, "step": 64}),
        ],
    ),
    (
        "Печатные листы",
        "Параметры сборки печатных листов (2x4 сетка фото).",
        [
            ("sheet", "photos_per_sheet", "Фото на лист",
             "Сколько фото помещается на один печатный лист.",
             "number", {"min": 1, "max": 20}),
            ("sheet", "min_photos_to_compose", "Мин. фото для сборки",
             "Не собирать лист, если фото меньше этого числа.",
             "number", {"min": 1, "max": 20}),
            ("sheet", "grid_columns", "Колонки сетки",
             "Число колонок в сетке печатного листа.",
             "number", {"min": 1, "max": 6}),
            ("sheet", "grid_rows", "Строки сетки",
             "Число строк в сетке печатного листа.",
             "number", {"min": 1, "max": 8}),
            ("sheet", "output_quality", "Качество JPEG (%)",
             "Качество сжатия выходных листов. 95 = высокое качество.",
             "range", {"min": 50, "max": 100, "step": 1}),
        ],
    ),
    (
        "Сеть",
        "Автосинхронизация в сетевую папку типографии.",
        [
            ("network", "auto_sync_sheets", "Автосинхронизация",
             "Автоматически копировать новые листы в сетевую папку после сборки.",
             "checkbox", {}),
            ("network", "output_path", "Сетевая папка",
             "Путь к общей папке (UNC или диск), куда копировать листы.",
             "text", {}),
        ],
    ),
    (
        "Печать",
        "Автоматическая печать готовых листов.",
        [
            ("print", "autoprint", "Автопечать",
             "Автоматически отправлять на печать каждый новый лист. Блокируется в тестовом режиме.",
             "checkbox", {}),
            ("print", "test_mode", "Тестовый режим",
             "В тестовом режиме листы формируются, но не печатаются. Включите для безопасной проверки.",
             "checkbox", {}),
            ("print", "printer_name", "Имя принтера",
             "Оставьте пустым для принтера по умолчанию.",
             "text", {}),
        ],
    ),
]


def _render_auth_modal(config: dict, error: str = "") -> str:
    """Render the login modal for settings access."""
    # Detect first run: password is still the default
    is_default_pw = config.get("auth", {}).get("settings_password", "1234") == "1234"
    if is_default_pw:
        hint = (
            '<div class="auth-hint">Это первый вход в настройки. '
            'Пароль по умолчанию: <b>1234</b>.<br>'
            'После входа настоятельно рекомендуется сменить пароль.</div>'
        )
    else:
        hint = '<div class="auth-hint">Настройки доступны только инженеру. Введите пароль для входа.</div>'

    error_html = ""
    if error:
        error_html = f'<div class="auth-error visible">{error}</div>'

    # Use a real HTML form (not fetch) so Set-Cookie works reliably in pywebview/WebView2
    body = (
        '<div class="auth-overlay">'
        '<div class="auth-modal">'
        '<a href="/" class="auth-close" title="Закрыть">&times;</a>'
        '<h2>&#128274; Доступ к настройкам</h2>'
        + hint +
        '<form method="POST" action="/api/auth-form">'
        '<input type="password" name="password" placeholder="Пароль" autofocus>'
        '<button type="submit" class="auth-btn">Войти</button>'
        '</form>'
        + error_html +
        '</div></div>'
    )
    return _page("Kanatka — Вход", body, active_nav="settings")


def _render_sheets_gallery(config: dict) -> str:
    """Render the sheets gallery page for test mode preview."""
    sheets_dir = Path(config["paths"]["output_sheets"])
    if not sheets_dir.exists():
        sheets_dir.mkdir(parents=True, exist_ok=True)

    sheet_files = sorted(
        sheets_dir.glob("*.jpg"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not sheet_files:
        body = '<h2 style="text-align:center; color:#999; margin-top:60px">Нет собранных листов</h2>'
        return _page("Kanatka — Листы", body, active_nav="sheets")

    cards = []
    for sf in sheet_files:
        mtime = sf.stat().st_mtime
        from datetime import datetime as _dt
        time_str = _dt.fromtimestamp(mtime).strftime("%d.%m.%Y %H:%M")
        size_kb = sf.stat().st_size // 1024
        thumb_url = f"/photo?path={sf.resolve()}&max_side=600"
        full_url = f"/photo?path={sf.resolve()}&max_side=3600"
        card = (
            '<div class="sheet-card">'
            f'<img src="{thumb_url}" onclick="openFullscreen(\'{full_url}\')" '
            f'style="cursor:pointer; width:100%; border-radius:8px">'
            f'<div style="margin-top:6px; font-size:13px; color:#666">'
            f'{sf.name}<br>{time_str} &middot; {size_kb} KB</div>'
            f'<button onclick="printSheet(\'{sf.name}\')" '
            f'style="margin-top:6px; padding:4px 12px; font-size:13px; '
            f'border:1px solid #ddd; border-radius:6px; background:#fff; cursor:pointer">'
            f'&#9113; Печать</button>'
            '</div>'
        )
        cards.append(card)

    print_cfg = config.get("print", {})
    mode_label = "TEST MODE" if print_cfg.get("test_mode", False) else "Рабочий режим"
    mode_color = "#f1c40f" if print_cfg.get("test_mode", False) else "#2ecc71"

    js = r"""
function printSheet(name) {
    if (!confirm('Отправить лист ' + name + ' на печать?')) return;
    fetch('/api/print-sheet', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({sheet: name})
    }).then(function(r) { return r.json(); }).then(function(d) {
        alert(d.status === 'ok' ? 'Лист отправлен на печать' : 'Ошибка: ' + (d.error || 'неизвестная'));
    });
}
"""

    body = (
        f'<h2>Собранные листы '
        f'<span style="font-size:14px; color:{mode_color}; font-weight:700">{mode_label}</span>'
        f'</h2>'
        f'<div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(280px, 1fr)); gap:16px">'
        + "".join(cards)
        + '</div>'
        f'<script>{js}</script>'
    )
    return _page("Kanatka — Листы", body, active_nav="sheets")


def _render_settings(config: dict) -> str:
    """Render the engineer settings page with all tunable parameters."""
    groups = []
    for group_title, group_desc, settings in _SETTINGS_SCHEMA:
        rows = []
        for section, key, label, hint, input_type, extra in settings:
            current = config.get(section, {}).get(key, "")
            field_id = f"{section}__{key}"

            if input_type == "range":
                mn = extra.get("min", 0)
                mx = extra.get("max", 100)
                st = extra.get("step", 1)
                val = float(current) if current != "" else mn
                control = (
                    f'<div style="display:flex; align-items:center; gap:8px">'
                    f'<input type="range" id="{field_id}" name="{field_id}_range"'
                    f' min="{mn}" max="{mx}" step="{st}" value="{val}"'
                    f' style="flex:1"'
                    f' oninput="document.getElementById(\'{field_id}_num\').value=this.value">'
                    f'<input type="number" id="{field_id}_num" name="{field_id}"'
                    f' min="{mn}" max="{mx}" step="{st}" value="{val}"'
                    f' style="width:70px; text-align:center; border:1px solid #ccc; border-radius:6px; padding:4px 6px; font-size:14px"'
                    f' oninput="document.getElementById(\'{field_id}\').value=this.value">'
                    f'</div>'
                )
            elif input_type == "number":
                mn = extra.get("min", 0)
                mx = extra.get("max", 9999)
                val = int(current) if current != "" else mn
                control = (
                    f'<input type="number" id="{field_id}" name="{field_id}"'
                    f' min="{mn}" max="{mx}" value="{val}">'
                )
            elif input_type == "checkbox":
                checked = "checked" if current else ""
                control = (
                    f'<input type="checkbox" id="{field_id}" name="{field_id}" {checked}>'
                )
            elif input_type == "text":
                val = str(current)
                control = (
                    f'<input type="text" id="{field_id}" name="{field_id}" value="{val}">'
                )
            else:
                control = str(current)

            rows.append(
                '<div class="setting-row">'
                '<div class="setting-label">'
                f'<div class="name">{label}</div>'
                f'<div class="hint">{hint}</div>'
                '</div>'
                f'<div class="setting-control">{control}</div>'
                '</div>'
            )

        groups.append(
            '<div class="settings-group">'
            f'<h3>{group_title}</h3>'
            f'<div class="group-desc">{group_desc}</div>'
            + "".join(rows)
            + '</div>'
        )

    save_js = r"""
function saveSettings() {
    var data = {};
    var inputs = document.querySelectorAll('.setting-control input, .setting-control select');
    for (var i = 0; i < inputs.length; i++) {
        var inp = inputs[i];
        // Skip range sliders — value comes from the paired number input
        if (inp.name.endsWith('_range')) continue;
        if (inp.type === 'checkbox') {
            data[inp.name] = inp.checked;
        } else {
            data[inp.name] = inp.value;
        }
    }
    fetch('/api/settings', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data),
        credentials: 'same-origin'
    }).then(function(resp) {
        var msg = document.getElementById('save-msg');
        if (resp.ok) {
            msg.textContent = 'Сохранено!';
            msg.className = 'save-msg visible';
            setTimeout(function() { msg.className = 'save-msg'; }, 3000);
        } else {
            msg.textContent = 'Ошибка сохранения';
            msg.style.color = '#e74c3c';
            msg.className = 'save-msg visible';
        }
    }).catch(function(e) {
        var msg = document.getElementById('save-msg');
        msg.textContent = 'Ошибка: ' + e.message;
        msg.style.color = '#e74c3c';
        msg.className = 'save-msg visible';
    });
}
"""

    is_default_pw = config.get("auth", {}).get("settings_password", "1234") == "1234"
    first_login_banner = ""
    if is_default_pw:
        first_login_banner = (
            '<div style="background:#fff3cd; border:1px solid #ffc107; border-radius:12px; '
            'padding:16px 20px; margin-bottom:20px; font-size:14px">'
            '&#9888; <b>Внимание:</b> установлен пароль по умолчанию. '
            'Рекомендуем сменить его прямо сейчас (раздел внизу страницы).'
            '</div>'
        )

    change_pw_html = (
        '<div class="change-pw-section" id="change-password">'
        '<h3>&#128275; Смена пароля</h3>'
        '<input type="password" id="pw-current" placeholder="Текущий пароль">'
        '<input type="password" id="pw-new" placeholder="Новый пароль">'
        '<input type="password" id="pw-confirm" placeholder="Подтвердите новый пароль">'
        '<button onclick="changePassword()">Сменить пароль</button>'
        '<div id="pw-msg" class="change-pw-msg"></div>'
        '</div>'
    )

    logout_btn = (
        '<a href="/logout" style="display:inline-block; margin-left:16px; color:#e74c3c; '
        'font-size:14px; text-decoration:none; font-weight:500;">Выйти</a>'
    )

    scroll_js = r"""
if (window.location.hash === '#change-password') {
    setTimeout(function() {
        var el = document.getElementById('change-password');
        if (el) { el.scrollIntoView({behavior: 'smooth'}); el.style.outline = '3px solid #ffc107'; }
    }, 300);
}
"""

    body = (
        '<div class="settings-page">'
        '<h2 style="margin-bottom:8px">Настройки инженера ' + logout_btn + '</h2>'
        + first_login_banner +
        '<p style="color:#666; margin-bottom:20px; font-size:14px">'
        'Параметры для полевой настройки программы. Изменения сохраняются в config.json.</p>'
        + "".join(groups)
        + '<div class="save-bar">'
        '<span id="save-msg" class="save-msg"></span>'
        '<button onclick="saveSettings()">Сохранить настройки</button>'
        '</div>'
        + change_pw_html
        + '</div>'
        f'<script>{save_js}\n{scroll_js}</script>'
    )
    return _page("Kanatka — Настройки", body, active_nav="settings")


# ---------------------------------------------------------------------------
# HTTP Server
# ---------------------------------------------------------------------------

class SeriesBrowserHandler(BaseHTTPRequestHandler):
    """HTTP handler for the series browser."""

    config: dict = {}
    _series_cache: list[dict] | None = None
    _cache_time: float = 0

    def log_message(self, format, *args):
        """Suppress default stderr logging."""
        pass

    def _get_series(self) -> list[dict]:
        """Load series with simple caching (refresh every 5 seconds)."""
        import time
        now = time.time()
        if SeriesBrowserHandler._series_cache is None or now - SeriesBrowserHandler._cache_time > 5:
            log_dir = Path(self.config["paths"]["log_dir"])
            SeriesBrowserHandler._series_cache = load_all_series(log_dir)
            SeriesBrowserHandler._cache_time = now
        return SeriesBrowserHandler._series_cache

    def _send_html(self, html: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        encoded = html.encode("utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_jpeg(self, data: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, data: dict, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        encoded = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_redirect(self, url: str) -> None:
        self.send_response(303)
        self.send_header("Location", url)
        self.end_headers()

    def _handle_cleanup(self, body: str) -> None:
        """Delete files from selected workdir subfolders."""
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"error": "invalid JSON"}, 400)
            return

        requested = data.get("folders", [])
        if not requested:
            self._send_json({"error": "no folders selected"}, 400)
            return

        # Map checkbox names to actual config paths
        folder_map = {
            "incoming": "input_folder",
            "selected": "output_selected",
            "rejected": "output_rejected",
            "discarded": "output_discarded",
            "ambiguous": "output_ambiguous",
            "sheets": "output_sheets",
            "archive": "output_archive",
            "logs": "log_dir",
        }

        total_deleted = 0
        for name in requested:
            config_key = folder_map.get(name)
            if not config_key:
                continue
            folder = Path(self.config["paths"].get(config_key, ""))
            if not folder.exists():
                continue
            import shutil
            for item in folder.iterdir():
                try:
                    if item.is_file():
                        item.unlink()
                        total_deleted += 1
                    elif item.is_dir():
                        shutil.rmtree(item)
                        total_deleted += 1
                except Exception:
                    pass

        # Clear series cache
        SeriesBrowserHandler._series_cache = None
        self._send_json({"status": "ok", "deleted": total_deleted})

    def _handle_monitor(self, body: str) -> None:
        """Start or stop INBOX monitoring."""
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"error": "invalid JSON"}, 400)
            return

        action = data.get("action", "")
        if action == "start":
            _start_monitoring(self.config)
            time.sleep(0.3)
            self._send_json(_MonitorState.status_dict())
        elif action == "stop":
            _stop_monitoring()
            time.sleep(0.3)
            self._send_json(_MonitorState.status_dict())
        elif action == "status":
            self._send_json(_MonitorState.status_dict())
        else:
            self._send_json({"error": "unknown action"}, 400)

    def _handle_auth(self, body: str) -> None:
        """Verify password and set auth cookie."""
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"error": "invalid JSON"}, 400)
            return

        password = data.get("password", "")
        stored = self.config.get("auth", {}).get("settings_password", "1234")

        if password == stored:
            token = _make_token()
            _auth_tokens.add(token)
            is_default = (stored == "1234")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Set-Cookie", f"kanatka_auth={token}; Path=/; HttpOnly; SameSite=Strict")
            resp = json.dumps({"status": "ok", "first_login": is_default}).encode("utf-8")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
        else:
            self._send_json({"error": "wrong password"}, 403)

    def _handle_auth_form(self, body: str) -> None:
        """Handle HTML form POST login — redirect-based auth for pywebview compatibility."""
        params = parse_qs(body)
        password = params.get("password", [""])[0]
        stored = self.config.get("auth", {}).get("settings_password", "1234")

        if password == stored:
            token = _make_token()
            _auth_tokens.add(token)
            is_default = (stored == "1234")
            redirect_to = "/settings#change-password" if is_default else "/settings"
            self.send_response(302)
            self.send_header("Location", redirect_to)
            self.send_header("Set-Cookie", f"kanatka_auth={token}; Path=/; HttpOnly; SameSite=Strict")
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            # Wrong password — show auth modal again with error
            html = _render_auth_modal(self.config, error="Неверный пароль")
            self._send_html(html)

    def _handle_change_password(self, body: str) -> None:
        """Change the settings password."""
        # Require auth
        cookie = self.headers.get("Cookie")
        if not _check_auth_cookie(cookie):
            self._send_json({"error": "unauthorized"}, 401)
            return

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"error": "invalid JSON"}, 400)
            return

        current = data.get("current", "")
        new_pw = data.get("new_password", "")
        stored = self.config.get("auth", {}).get("settings_password", "1234")

        if current != stored:
            self._send_json({"error": "wrong current password"}, 403)
            return

        if len(new_pw) < 4:
            self._send_json({"error": "too short"}, 400)
            return

        if "auth" not in self.config:
            self.config["auth"] = {}
        self.config["auth"]["settings_password"] = new_pw
        save_config(self.config)
        self._send_json({"status": "ok"})

    def _handle_save_settings(self, body: str) -> None:
        """Parse settings JSON and save to config."""
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"error": "invalid JSON"}, 400)
            return

        # Map field_id ("section__key") back to config sections
        for field_id, value in data.items():
            parts = field_id.split("__", 1)
            if len(parts) != 2:
                continue
            section, key = parts
            if section not in self.config:
                self.config[section] = {}

            # Type coercion based on what's in current config
            current = self.config[section].get(key)
            if isinstance(current, bool) or isinstance(value, bool):
                self.config[section][key] = bool(value)
            elif isinstance(current, int):
                try:
                    self.config[section][key] = int(float(value))
                except (ValueError, TypeError):
                    pass
            elif isinstance(current, float):
                try:
                    self.config[section][key] = float(value)
                except (ValueError, TypeError):
                    pass
            else:
                self.config[section][key] = str(value)

        save_config(self.config)
        self._send_json({"status": "ok"})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        params = parse_qs(parsed.query)

        if path == "/":
            series = self._get_series()
            page = int(params.get("page", ["1"])[0])
            filter_status = params.get("filter", [""])[0]
            html = _render_series_list(series, page=page, filter_status=filter_status)
            self._send_html(html)

        elif path.startswith("/series/"):
            series_name = path.split("/series/", 1)[1]
            series = self._get_series()
            found = next((s for s in series if s.get("series") == series_name), None)
            if found:
                selected_dir = Path(self.config["paths"]["output_selected"])
                html = _render_series_detail(found, selected_dir)
                self._send_html(html)
            else:
                self._send_html("<h1>Серия не найдена</h1>", 404)

        elif path.startswith("/nearby/"):
            series_name = path.split("/nearby/", 1)[1]
            series = self._get_series()
            found = next((s for s in series if s.get("series") == series_name), None)
            if found:
                selected_dir = Path(self.config["paths"]["output_selected"])
                html = _render_nearby(found, series, selected_dir)
                self._send_html(html)
            else:
                self._send_html("<h1>Серия не найдена</h1>", 404)

        elif path == "/sheets":
            html = _render_sheets_gallery(self.config)
            self._send_html(html)

        elif path == "/settings":
            # Check auth
            cookie = self.headers.get("Cookie")
            if _check_auth_cookie(cookie):
                html = _render_settings(self.config)
            else:
                html = _render_auth_modal(self.config)
            self._send_html(html)

        elif path == "/logout":
            # Clear auth token from cookie
            cookie = self.headers.get("Cookie")
            if cookie:
                for part in cookie.split(";"):
                    part = part.strip()
                    if part.startswith("kanatka_auth="):
                        token = part.split("=", 1)[1]
                        _auth_tokens.discard(token)
            self.send_response(303)
            self.send_header("Location", "/settings")
            self.send_header("Set-Cookie", "kanatka_auth=; Path=/; Max-Age=0")
            self.end_headers()

        elif path == "/photo":
            file_path = params.get("path", [""])[0]
            max_side = int(params.get("max_side", ["400"])[0])
            if not file_path:
                self.send_error(400)
                return
            file_path = unquote(file_path)
            real_path = Path(file_path)
            if not real_path.exists():
                inbox = Path(self.config["paths"]["test_photos_folder"])
                if not inbox.is_absolute():
                    inbox = Path.cwd() / inbox
                real_path = inbox / real_path.name
            if real_path.exists() and real_path.suffix.lower() in {".jpg", ".jpeg"}:
                try:
                    data = _thumb_bytes(real_path, max_side)
                    self._send_jpeg(data)
                except Exception:
                    self.send_error(500)
            else:
                self.send_error(404)

        else:
            self.send_error(404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8")

        if parsed.path == "/api/cleanup":
            self._handle_cleanup(body)
            return

        if parsed.path == "/api/monitor":
            self._handle_monitor(body)
            return

        if parsed.path == "/api/auth":
            self._handle_auth(body)
            return

        if parsed.path == "/api/auth-form":
            self._handle_auth_form(body)
            return

        if parsed.path == "/api/change-password":
            self._handle_change_password(body)
            return

        if parsed.path == "/api/settings":
            # Require auth for saving settings
            cookie = self.headers.get("Cookie")
            if not _check_auth_cookie(cookie):
                self._send_json({"error": "unauthorized"}, 401)
                return
            self._handle_save_settings(body)
            return

        if parsed.path == "/api/confirm-ambiguous":
            try:
                data = json.loads(body) if body else {}
            except json.JSONDecodeError:
                data = {}
            series_name = data.get("series", "")
            if not series_name:
                self._send_json({"error": "missing series"}, 400)
                return
            ok = confirm_ambiguous(series_name, self.config)
            if ok:
                SeriesBrowserHandler._series_cache = None
                self._send_json({"status": "ok"})
            else:
                self._send_json({"error": "not found or already confirmed"}, 404)
            return

        if parsed.path == "/api/print-sheet":
            try:
                data = json.loads(body) if body else {}
            except json.JSONDecodeError:
                data = {}
            sheet_name = data.get("sheet", "")
            if not sheet_name:
                self._send_json({"error": "missing sheet name"}, 400)
                return
            sheets_dir = Path(self.config["paths"]["output_sheets"])
            sheet_path = sheets_dir / sheet_name
            if not sheet_path.exists():
                self._send_json({"error": "sheet not found"}, 404)
                return
            print_cfg = self.config.get("print", {})
            if print_cfg.get("test_mode", True):
                self._send_json({"error": "печать заблокирована в тестовом режиме"}, 400)
                return
            from print_utils import print_sheet
            ok = print_sheet(sheet_path, print_cfg.get("printer_name", ""))
            if ok:
                self._send_json({"status": "ok"})
            else:
                self._send_json({"error": "print failed"}, 500)
            return

        params = parse_qs(body)

        if parsed.path == "/rescue":
            # Single photo rescue (from series detail page)
            file_path = params.get("path", [""])[0]
            series_name = params.get("series", [""])[0]

            if file_path and series_name:
                source = Path(file_path)
                if not source.exists():
                    inbox = Path(self.config["paths"]["test_photos_folder"])
                    if not inbox.is_absolute():
                        inbox = Path.cwd() / inbox
                    source = inbox / source.name
                if source.exists():
                    selected_dir = Path(self.config["paths"]["output_selected"])
                    dest = rescue_photo(source, selected_dir, series_name)
                    _sync_rescued_to_network([dest], self.config)
                    SeriesBrowserHandler._series_cache = None

            self._send_redirect(f"/series/{series_name}")

        elif parsed.path == "/rescue-batch":
            # Batch rescue from nearby browser
            count = int(params.get("count", ["0"])[0])
            redirect_to = params.get("redirect", ["/"])[0]

            photos_to_rescue = []
            for i in range(count):
                fpath = params.get(f"path_{i}", [""])[0]
                series_name = params.get(f"series_{i}", [""])[0]
                if fpath and series_name:
                    photos_to_rescue.append({
                        "path": fpath,
                        "series": series_name,
                    })

            if photos_to_rescue:
                selected_dir = Path(self.config["paths"]["output_selected"])
                rescue_batch(photos_to_rescue, selected_dir, self.config)
                SeriesBrowserHandler._series_cache = None

            self._send_redirect(redirect_to)

        else:
            self.send_error(404)


def _kill_old_server(port: int) -> None:
    """Kill any existing process listening on the given port (Windows only)."""
    import subprocess
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            if f"127.0.0.1:{port}" in line and "LISTENING" in line:
                parts = line.split()
                pid = parts[-1]
                if pid.isdigit() and int(pid) != 0:
                    subprocess.run(
                        ["taskkill", "/F", "/PID", pid],
                        capture_output=True, timeout=5,
                    )
    except Exception:
        pass


def start_server(config: dict, port: int = 8787) -> threading.Thread:
    """Start the series browser HTTP server WITHOUT opening a browser."""
    _kill_old_server(port)
    import time
    time.sleep(0.3)

    SeriesBrowserHandler.config = config
    SeriesBrowserHandler._series_cache = None

    server = ThreadingHTTPServer(("127.0.0.1", port), SeriesBrowserHandler)
    server.daemon_threads = True

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def start_browser(config: dict, port: int = 8787) -> threading.Thread:
    """Start the series browser HTTP server and open the default browser."""
    thread = start_server(config, port)
    webbrowser.open(f"http://127.0.0.1:{port}")
    return thread
