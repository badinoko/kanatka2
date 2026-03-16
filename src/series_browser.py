"""Web-based series browser for reviewing and rescuing photos.

Runs a local HTTP server (stdlib only, no dependencies) that shows
all processed series with thumbnails, scores, and rescue controls.
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
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from PIL import Image

from badge_utils import DEBUG_COLUMNS
from config_utils import ensure_runtime_directories, save_config
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


class _SimulatorState:
    """Tracks whether the inbox simulator is currently running."""
    running: bool = False
    thread: threading.Thread | None = None

    @classmethod
    def is_active(cls) -> bool:
        return cls.running and cls.thread is not None and cls.thread.is_alive()


def _run_inbox_simulation(config: dict, initial_delay: float = 5.0) -> None:
    """Background thread: copy files from INBOX to incoming with realistic delays.

    This is a demo/testing convenience — simulates how the real camera would
    deliver files in batches.  Remove or disable before production deployment.
    """
    import random as _random
    import shutil as _shutil
    import time as _time
    from datetime import datetime as _dt

    from config_utils import get_project_root
    from image_utils import list_image_files

    _SimulatorState.running = True
    logger = build_logger(
        config["paths"]["log_dir"],
        log_to_file=config.get("logging", {}).get("log_to_file", True),
    )
    try:
        inbox_dir = Path(config["paths"]["test_photos_folder"])
        if not inbox_dir.is_absolute():
            inbox_dir = get_project_root() / inbox_dir

        incoming_dir = Path(config["paths"]["input_folder"])
        if not incoming_dir.is_absolute():
            incoming_dir = get_project_root() / incoming_dir
        incoming_dir.mkdir(parents=True, exist_ok=True)

        _time.sleep(initial_delay)

        files = list_image_files(inbox_dir)
        if not files:
            logger.warning("Симулятор INBOX: папка пуста, нечего отправлять")
            return

        rng = _random.Random(42)
        rng.shuffle(files)
        series_size = 8
        series_list = [files[i:i + series_size] for i in range(0, len(files), series_size)]
        logger.info("Симулятор INBOX: %d серий, %d файлов", len(series_list), len(files))

        for s_idx, series in enumerate(series_list, 1):
            for f_idx, photo_path in enumerate(series, 1):
                timestamp = _dt.now().strftime("%Y%m%d_%H%M%S_%f")
                target_name = f"SIM{s_idx:03d}_IMG{f_idx:03d}_{timestamp}{photo_path.suffix.lower()}"
                _shutil.copy(photo_path, incoming_dir / target_name)
                logger.info("Симулятор: серия %d/%d кадр %d/%d → %s",
                            s_idx, len(series_list), f_idx, len(series), target_name)
                _time.sleep(0.2)
            if s_idx != len(series_list):
                delay = rng.uniform(3.0, 4.0)
                logger.info("Симулятор: пауза %.1f сек", delay)
                _time.sleep(delay)

        logger.info("Симулятор INBOX завершён: %d серий", len(series_list))
    finally:
        _SimulatorState.running = False


def _start_monitoring(config: dict) -> None:
    """Start watching the incoming folder in a background thread."""
    if _MonitorState.is_active():
        return

    try:
        from watcher import (
            IncomingFolderHandler,
            PendingQueue,
            group_files_by_time,
        )
        from face_utils import MediaPipeFaceAnalyzer
        from selector import process_series
        from sheet_composer import compose_pending_sheets
        from watchdog.observers import Observer
    except ImportError as exc:
        _MonitorState.running = False
        _MonitorState.error = f"Не удалось загрузить зависимости мониторинга: {exc}"
        return
    except Exception as exc:
        _MonitorState.running = False
        _MonitorState.error = f"Не удалось подготовить мониторинг: {exc}"
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
        logger = build_logger(config["paths"]["log_dir"], log_to_file=config.get("logging", {}).get("log_to_file", True))
        logger.info("Автономный режим: мониторинг %s", incoming_dir)
        observer = None
        analyzer = None
        try:
            analyzer = MediaPipeFaceAnalyzer(config["thresholds"]["min_face_confidence"])
            pending = PendingQueue()
            observer = Observer()
            observer.schedule(IncomingFolderHandler(pending), str(incoming_dir), recursive=False)
            observer.start()
            _MonitorState.observer = observer
            # Pre-populate queue with files already in incoming/ before monitoring started
            for _pattern in ("*.jpg", "*.jpeg", "*.png"):
                for _f in incoming_dir.glob(_pattern):
                    pending.add(_f)
        except Exception as exc:
            logger.exception("Ошибка запуска мониторинга: %s", exc)
            _MonitorState.error = f"Мониторинг не запущен: {exc}"
            _MonitorState.running = False
            if observer is not None:
                try:
                    observer.stop()
                    observer.join()
                except Exception:
                    pass
            if analyzer is not None:
                try:
                    analyzer.close()
                except Exception:
                    pass
            return

        # Continue numbering from the highest existing series in logs/ to avoid
        # overwriting old reports and corrupting the reverse-chronological sort.
        import re as _re
        _log_dir = Path(config["paths"]["log_dir"])
        _max_idx = 0
        for _rp in _log_dir.glob("s_*_report.json"):
            _m = _re.match(r"s_(\d+)_report", _rp.stem)
            if _m:
                _max_idx = max(_max_idx, int(_m.group(1)))
        series_idx = _max_idx + 1
        try:
            while _MonitorState.running:
                ready = pending.flush_ready(config["series_detection"]["cooldown_seconds"])
                if ready:
                    grouped = group_files_by_time(ready, config["series_detection"]["max_gap_seconds"])
                    for group in grouped:
                        if not _MonitorState.running:
                            break
                        try:
                            process_series(
                                group, series_idx, analyzer, config, logger,
                                remove_source_files=False, save_annotations=True,
                            )
                            compose_pending_sheets(config, logger)
                        except Exception as _series_exc:
                            logger.warning("Серия %d пропущена из-за ошибки: %s", series_idx, _series_exc)
                        _MonitorState.series_count += 1
                        _MonitorState.last_activity = time.strftime("%H:%M:%S")
                        # Invalidate series cache
                        SeriesBrowserHandler._series_cache = None
                        series_idx += 1
                time.sleep(0.5)
        except Exception as exc:
            logger.exception("Ошибка во время мониторинга: %s", exc)
            _MonitorState.error = str(exc)
        finally:
            if observer is not None:
                observer.stop()
                observer.join()
            if analyzer is not None:
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
    """Read all s_*_report.json files and return sorted list of series."""
    series: list[dict] = []
    for report_path in sorted(log_dir.glob("s_*_report.json"), reverse=True):
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
    """Rescue multiple photos into the selected directory.

    Utility function for batch rescue operations. Kept for testing and potential
    future use; the /rescue-batch HTTP endpoint was removed in KAN-081.

    Each item in photos: {"path": str, "series": str}
    Returns list of destination paths.
    """
    selected_dir.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for item in photos:
        source = Path(item["path"])
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
    for report_path in log_dir.glob("s_*_report.json"):
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


def _resolve_runtime_path(config: dict, key: str) -> Path:
    path = Path(config["paths"].get(key, ""))
    if not path.is_absolute():
        from config_utils import get_project_root
        path = get_project_root() / path
    return path


def _find_existing_photo_for_series(
    photo: dict,
    series_name: str,
    config: dict,
    selected_file: str = "",
) -> Path | None:
    file_name = photo.get("file_name", "")
    file_path = photo.get("file_path", "")

    direct = Path(file_path) if file_path else None
    if direct and direct.exists():
        return direct

    input_folder = _resolve_runtime_path(config, "input_folder")
    if file_name:
        inbox_candidate = input_folder / file_name
        if inbox_candidate.exists():
            return inbox_candidate

    if selected_file and file_name and selected_file == f"{series_name}_{file_name}":
        selected_candidate = _resolve_runtime_path(config, "output_selected") / selected_file
        if selected_candidate.exists():
            return selected_candidate

    return None


def _series_has_live_assets(series: dict, config: dict) -> bool:
    selected_file = series.get("selected_file", "")
    series_name = series.get("series", "")
    photos = series.get("photos", [])

    if selected_file:
        for path_key in ("output_selected", "output_archive"):
            candidate = _resolve_runtime_path(config, path_key) / selected_file
            if candidate.exists():
                return True

    for photo in photos:
        if _find_existing_photo_for_series(photo, series_name, config, selected_file=selected_file):
            return True
    return False


def _find_rescue_source(photo: dict, config: dict) -> Path | None:
    file_name = photo.get("file_name", "")
    file_path = photo.get("file_path", "")
    input_folder = _resolve_runtime_path(config, "input_folder")
    return _find_photo_path(file_path, input_folder, file_name)


def _series_visibility(all_series: list[dict], config: dict) -> tuple[list[dict], list[dict]]:
    live_series: list[dict] = []
    history_series: list[dict] = []
    for series in all_series:
        if _series_has_live_assets(series, config):
            live_series.append(series)
        else:
            history_series.append(series)
    return live_series, history_series


def _resolve_series_card_thumb(series: dict, config: dict) -> Path | None:
    selected_file = series.get("selected_file", "")
    series_name = series.get("series", "")
    if selected_file:
        for path_key in ("output_selected", "output_archive"):
            candidate = _resolve_runtime_path(config, path_key) / selected_file
            if candidate.exists():
                return candidate
    # Fallback: try photos sorted by score descending so the best available is shown
    photos_by_score = sorted(
        series.get("photos", []),
        key=lambda p: p.get("score", 0) if isinstance(p.get("score"), (int, float)) else 0,
        reverse=True,
    )
    for photo in photos_by_score:
        existing = _find_existing_photo_for_series(photo, series_name, config, selected_file=selected_file)
        if existing:
            return existing
    return None


def _thumb_bytes(image_path: Path, max_side: int = 400) -> bytes:
    """Load an image and return JPEG thumbnail bytes."""
    with Image.open(image_path) as img:
        img = img.convert("RGB")
        img.thumbnail((max_side, max_side), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        return buf.getvalue()


def _build_lightbox_debug_html(photo: dict) -> str:
    """Build rich HTML for score inspection inside the lightbox."""
    score = photo.get("score", 0.0)
    score_val = float(score) if isinstance(score, (int, float)) else 0.0
    breakdown = photo.get("score_breakdown", {}) or {}
    weights = photo.get("scoring_weights", {}) or {}
    detect_info = _detect_label(
        bool(photo.get("subject_present", False)),
        bool(photo.get("person_fallback", False)),
    )
    quality_gate = breakdown.get("quality_gate", "n/a")
    readable_faces = photo.get("readable_face_count", 0)
    rows = []

    for key, label in DEBUG_COLUMNS:
        raw_value = breakdown.get(key, 0.0)
        numeric_value = float(raw_value) if isinstance(raw_value, (int, float)) else 0.0
        weight_value = float(weights.get(key, 0.0)) if isinstance(weights.get(key, 0.0), (int, float)) else 0.0
        rows.append(
            '<div class="lightbox-debug-row">'
            f'<span class="debug-label">{escape(label)}</span>'
            f'<span class="debug-raw">{numeric_value:.2f}</span>'
            f'<span class="debug-points">+{numeric_value * weight_value:.1f}</span>'
            '</div>'
        )

    if isinstance(breakdown.get("smile_bonus"), (int, float)) and "smile_bonus" in weights:
        smile = float(breakdown["smile_bonus"])
        smile_weight = float(weights.get("smile_bonus", 0.0))
        rows.append(
            '<div class="lightbox-debug-row">'
            '<span class="debug-label">Улыбка</span>'
            f'<span class="debug-raw">{smile:.2f}</span>'
            f'<span class="debug-points">+{smile * smile_weight:.1f}</span>'
            '</div>'
        )

    if not rows:
        rows.append('<div class="lightbox-debug-empty">Нет breakdown-данных для этого кадра.</div>')

    return (
        '<div class="lightbox-debug-summary">'
        f'<span><b>Gate:</b> {escape(str(quality_gate))}</span>'
        f'<span><b>Детекция:</b> {escape(detect_info)}</span>'
        f'<span><b>Лиц читаемо:</b> {int(readable_faces) if isinstance(readable_faces, (int, float)) else 0}</span>'
        '</div>'
        '<div class="lightbox-debug-table">'
        + "".join(rows)
        + '</div>'
    )


def _build_inline_debug_html(photo: dict) -> str:
    """Compact score breakdown shown below photo cards when debug mode is enabled."""
    breakdown = photo.get("score_breakdown", {}) or {}
    chips = []
    for key, label in DEBUG_COLUMNS:
        raw_value = breakdown.get(key)
        if not isinstance(raw_value, (int, float)):
            continue
        chips.append(
            '<span class="debug-chip">'
            f'{escape(label)}: <b>{float(raw_value):.2f}</b>'
            '</span>'
        )
    if isinstance(breakdown.get("smile_bonus"), (int, float)):
        chips.append(
            '<span class="debug-chip">'
            f'Улыбка: <b>{float(breakdown["smile_bonus"]):.2f}</b>'
            '</span>'
        )
    if not chips:
        return ""
    return '<div class="debug-breakdown">' + "".join(chips) + '</div>'


def _build_lightbox_payload_attr(src: str, title: str, subtitle: str, debug_html: str = "", score: float = 0.0, score_label: str = "") -> str:
    payload = json.dumps(
        {
            "src": src,
            "title": title,
            "subtitle": subtitle,
            "debug_html": debug_html,
            "score": score,
            "score_label": score_label,
        },
        ensure_ascii=False,
    )
    return escape(payload, quote=True)


# ---------------------------------------------------------------------------
# HTML Templates
# ---------------------------------------------------------------------------

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
html { overflow-y: scroll; }
body { font-family: -apple-system, 'Segoe UI', Arial, sans-serif; background: #f0f2f5; color: #1a1a1a; padding-top: 64px; }

/* Sticky Navigation — v3 redesign */
.navbar { position: fixed; top: 0; left: 0; right: 0; z-index: 900; background: #1a1a2e; color: #fff;
          height: 64px; display: flex; align-items: center; padding: 0 20px; box-shadow: 0 2px 12px rgba(0,0,0,0.25); gap: 12px; }
.navbar .brand { font-size: 20px; font-weight: 700; color: #fff; text-decoration: none; white-space: nowrap; margin-right: 4px; }
.navbar .brand span { font-size: 22px; }

/* Page switcher pill */
.page-switcher { display: flex; background: rgba(255,255,255,0.08); border-radius: 10px; padding: 3px; gap: 2px; flex-shrink: 0; }
.page-switcher a { text-decoration: none; color: rgba(255,255,255,0.6); padding: 8px 18px; border-radius: 8px;
                   font-size: 14px; font-weight: 600; transition: all 0.2s; white-space: nowrap; }
.page-switcher a.active { background: rgba(255,255,255,0.18); color: #fff; }
.page-switcher a:hover:not(.active) { background: rgba(255,255,255,0.08); color: rgba(255,255,255,0.85); }

/* Nav divider */
.nav-divider { width: 1px; height: 28px; background: rgba(255,255,255,0.15); margin: 0 4px; flex-shrink: 0; }

/* Action buttons — icon-only with tooltips */
.action-buttons { display: flex; gap: 4px; flex-shrink: 0; }
.action-btn { width: 42px; height: 42px; display: flex; align-items: center; justify-content: center;
              background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.10); border-radius: 10px;
              color: rgba(255,255,255,0.75); font-size: 22px; line-height: 1; cursor: pointer; transition: all 0.15s;
              position: relative; flex-shrink: 0; }
.action-btn:hover { background: rgba(255,255,255,0.14); color: #fff; transform: translateY(-1px); }
.action-btn.active-toggle { background: rgba(255,193,7,0.2); border-color: rgba(255,193,7,0.4); color: #ffc107; }
.action-btn.danger { color: rgba(239,83,80,0.85); }
.action-btn.danger:hover { background: rgba(239,83,80,0.15); color: #ef5350; }
.action-btn::after { content: attr(data-tooltip); position: absolute; bottom: -32px; left: 50%;
                     transform: translateX(-50%); background: #333; color: #fff; padding: 4px 10px;
                     border-radius: 6px; font-size: 12px; white-space: nowrap;
                     opacity: 0; pointer-events: none; transition: opacity 0.15s; z-index: 999; }
.action-btn:hover::after { opacity: 1; }

/* Monitor button — hero element in navbar */
.monitor-btn { display: flex; align-items: center; gap: 8px; padding: 8px 20px; border-radius: 10px;
               font-size: 14px; font-weight: 700; cursor: pointer; transition: all 0.2s;
               border: 2px solid; white-space: nowrap; flex-shrink: 0; background: none; }
.monitor-btn.start { background: rgba(76,175,80,0.12); border-color: rgba(76,175,80,0.5); color: #66bb6a; }
.monitor-btn.start:hover { background: rgba(76,175,80,0.25); border-color: #66bb6a; }
.monitor-btn.stop { background: rgba(76,175,80,0.15); border-color: #4caf50; color: #81c784; }
.monitor-btn.stop:hover { background: rgba(239,83,80,0.15); border-color: #ef5350; color: #ef5350; }
.pulse-dot { width: 10px; height: 10px; background: #4caf50; border-radius: 50%; flex-shrink: 0;
             animation: pulse 1.5s ease-in-out infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(76,175,80,0.6); }
                   50% { opacity: 0.8; box-shadow: 0 0 0 6px rgba(76,175,80,0); } }

.nav-spacer { flex: 1; min-width: 8px; }
.navbar .nav-right { font-size: 13px; display: flex; align-items: center; gap: 10px; flex-shrink: 0; }

/* Settings gear */
.settings-btn { width: 44px; height: 44px; display: flex; align-items: center; justify-content: center;
                background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.10);
                border-radius: 10px; color: rgba(255,255,255,0.7); font-size: 22px; cursor: pointer;
                transition: all 0.2s; flex-shrink: 0; text-decoration: none; }
.settings-btn:hover { background: rgba(255,255,255,0.14); color: #fff; transform: rotate(30deg); }

/* Disk indicator */
.disk-indicator { display: flex; align-items: center; gap: 5px; color: rgba(255,255,255,0.65);
                  font-size: 13px; white-space: nowrap; }
.disk-indicator .icon { font-size: 16px; }
.stats-badge { color: rgba(255,255,255,0.55); font-size: 12px; white-space: nowrap; }

/* Responsive: hide stats text at narrow widths */
@media (max-width: 1400px) { .stats-badge { display: none; } }
@media (max-width: 1100px) { .disk-indicator .disk-text { display: none; }
                             .monitor-btn { padding: 8px 14px; font-size: 13px; } }

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

/* Series detail */
.photo-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.photo-card { background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); position: relative; }
.photo-card img.photo-thumb { width: 100%; height: 220px; object-fit: cover; cursor: pointer; }
.photo-card img.photo-thumb:hover { opacity: 0.9; }
.photo-info { padding: 12px 16px; }
.photo-name { font-size: 13px; color: #888; word-break: break-all; margin-bottom: 6px; }
.photo-score { font-size: 16px; font-weight: 600; margin-bottom: 8px; }
.debug-breakdown { display: none; gap: 6px; flex-wrap: wrap; margin-top: 10px; }
body.debug-enabled .debug-breakdown { display: flex; }
.debug-chip { display: inline-flex; gap: 4px; align-items: center; background: #eef3ff; color: #1f355f; border: 1px solid #d7e2ff;
              border-radius: 999px; padding: 4px 9px; font-size: 12px; }
.rescue-btn { display: inline-block; background: #3498db; color: #fff; border: none; padding: 8px 20px;
              border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; text-decoration: none; }
.rescue-btn:hover { background: #2980b9; }
.rescue-btn.done { background: #2ecc71; cursor: default; }
.fullscreen-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
                      background: rgba(0,0,0,0.92); z-index: 1000; justify-content: center; align-items: center; padding: 24px; }
.fullscreen-overlay.active { display: flex; }
.lightbox-shell { width: min(1600px, 100%); height: min(94vh, 1120px); display: grid; grid-template-columns: minmax(0, 1fr) 300px;
                  background: #0f1723; border-radius: 18px; overflow: hidden; box-shadow: 0 24px 60px rgba(0,0,0,0.45); }
.lightbox-main { position: relative; display: flex; align-items: center; justify-content: center; background: #05080d; min-width: 0; overflow: hidden; }
.lightbox-main img { max-width: 100%; max-height: 100%; object-fit: contain; }
.lightbox-close { position: absolute; top: 16px; right: 16px; width: 42px; height: 42px; border-radius: 50%; border: none;
                  background: rgba(255,255,255,0.14); color: #fff; cursor: pointer; font-size: 24px; line-height: 1; z-index: 10; }
.lightbox-close:hover { background: rgba(255,255,255,0.24); }
.lightbox-nav { position: absolute; top: 50%; transform: translateY(-50%); width: 48px; height: 48px; border-radius: 50%; border: none;
                background: rgba(255,255,255,0.12); color: #fff; cursor: pointer; font-size: 26px; line-height: 1; z-index: 10; }
.lightbox-nav:hover:not(:disabled) { background: rgba(255,255,255,0.22); }
.lightbox-nav:disabled { opacity: 0.28; cursor: default; }
.lightbox-nav.prev { left: 16px; }
.lightbox-nav.next { right: 16px; }
.lightbox-side { background: #121a26; color: #f6f8fb; padding: 24px 20px; overflow-y: auto; border-left: 1px solid rgba(255,255,255,0.08); }
.lightbox-title { font-size: 18px; font-weight: 700; margin-bottom: 6px; word-break: break-word; }
.lightbox-subtitle { font-size: 13px; color: #aebacf; margin-bottom: 12px; line-height: 1.5; }
.lightbox-counter { display: inline-block; background: rgba(255,255,255,0.08); border-radius: 999px; padding: 5px 10px;
                    font-size: 12px; margin-bottom: 18px; }
.lightbox-hint { font-size: 12px; color: #8b97aa; margin-top: 12px; line-height: 1.5; }
.lightbox-score { margin-bottom: 14px; }
.lightbox-score-value { font-size: 38px; font-weight: 800; line-height: 1; }
.lightbox-score-denom { font-size: 13px; color: #8b97aa; margin-left: 4px; }
.lightbox-debug-panel { display: none; }
body.debug-enabled .lightbox-debug-panel { display: block; }
.lightbox-debug-summary { display: grid; gap: 8px; margin-bottom: 16px; font-size: 13px; }
.lightbox-debug-table { display: grid; gap: 8px; }
.lightbox-debug-row { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: 10px; align-items: center;
                      background: rgba(255,255,255,0.05); border-radius: 10px; padding: 8px 10px; font-size: 13px; }
.lightbox-debug-row .debug-label { color: #d9e2ef; }
.lightbox-debug-row .debug-raw { color: #9fc2ff; font-variant-numeric: tabular-nums; }
.lightbox-debug-row .debug-points { color: #f8d57f; font-weight: 700; font-variant-numeric: tabular-nums; }
.lightbox-debug-empty { color: #8b97aa; font-size: 13px; }
.rescued-badge { display: inline-block; background: #2ecc71; color: #fff; padding: 2px 10px; border-radius: 12px; font-size: 12px; margin-left: 8px; }

@media (max-width: 1024px) {
  .lightbox-shell { grid-template-columns: 1fr; height: auto; max-height: 92vh; }
  .lightbox-main { min-height: 50vh; }
  .lightbox-side { border-left: none; border-top: 1px solid rgba(255,255,255,0.08); }
}


/* Settings page */
.settings-layout { display: flex; gap: 24px; max-width: 1100px; margin: 0 auto; }
.settings-sidebar { position: sticky; top: 80px; flex: 0 0 180px; align-self: flex-start; }
.settings-sidebar nav { background: #fff; border-radius: 12px; padding: 12px 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.settings-sidebar a { display: block; padding: 8px 12px; font-size: 13px; color: #555; text-decoration: none;
                      border-radius: 8px; margin-bottom: 2px; transition: all 0.15s; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.settings-sidebar a:hover { background: #f0f2f5; color: #1a1a2e; }
.settings-sidebar a.active { background: #4a6fa5; color: #fff; font-weight: 600; }
.settings-main { flex: 1; min-width: 0; }
.settings-page { max-width: 900px; margin: 0 auto; }
.settings-group { background: #fff; border-radius: 12px; padding: 20px 24px; margin-bottom: 20px;
                  box-shadow: 0 2px 8px rgba(0,0,0,0.06); scroll-margin-top: 80px; }
.settings-group h3 { font-size: 16px; font-weight: 600; margin-bottom: 4px; color: #1a1a2e; }
.settings-group .group-desc { font-size: 13px; color: #666; margin-bottom: 16px; }
@media (max-width: 860px) { .settings-sidebar { display: none; } .settings-layout { max-width: 900px; } }
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

/* Unified modal styles */
.modal-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
                 background: rgba(0,0,0,0.5); z-index: 9999; align-items: center; justify-content: center; }
.modal-content { background: #fff; border-radius: 16px; padding: 0; width: 90%;
                 box-shadow: 0 12px 48px rgba(0,0,0,0.25), 0 4px 16px rgba(0,0,0,0.15);
                 position: relative; animation: modalIn 0.2s ease-out; }
@keyframes modalIn { from { opacity: 0; transform: translateY(12px) scale(0.97); } to { opacity: 1; transform: none; } }
.modal-header { display: flex; align-items: center; justify-content: space-between; padding: 20px 28px 0; }
.modal-header h3 { margin: 0; font-size: 17px; font-weight: 600; color: #1a1a2e; }
.modal-close { width: 32px; height: 32px; display: flex; align-items: center; justify-content: center;
               background: #f0f2f5; border: none; border-radius: 8px; font-size: 20px; color: #666;
               cursor: pointer; transition: all 0.15s; line-height: 1; flex-shrink: 0; }
.modal-close:hover { background: #e0e0e0; color: #333; }
.modal-body { padding: 16px 28px 24px; }
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
.view-switcher { display: flex; gap: 3px; background: rgba(255,255,255,0.06); border-radius: 8px; padding: 3px; }
/* Toast notification */
#toast { position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
         background: #22313f; color: #fff; padding: 14px 28px; border-radius: 12px;
         font-size: 15px; font-weight: 500; z-index: 99999; box-shadow: 0 6px 24px rgba(0,0,0,0.35);
         opacity: 0; transition: opacity 0.25s; pointer-events: none;
         max-width: 600px; text-align: center; white-space: pre-wrap; }
#toast.toast-ok { background: #27ae60; }
#toast.toast-err { background: #e74c3c; }
#toast.show { opacity: 1; }
.view-switcher button { width: 34px; height: 34px; display: flex; align-items: center; justify-content: center;
                        background: transparent; border: none; color: rgba(255,255,255,0.5);
                        border-radius: 6px; cursor: pointer; font-size: 16px; transition: all 0.15s; }
.view-switcher button:hover { background: rgba(255,255,255,0.15); color: #fff; }
.view-switcher button.active { background: rgba(255,255,255,0.15); color: #fff; }
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
var lightboxState = { active: false, group: '', items: [], index: 0 };

function getDebugMode() {
    var stored = localStorage.getItem('kanatka_debug_score');
    if (stored === null) return !!window.KANATKA_DEBUG_DEFAULT;
    return stored === '1';
}
function applyDebugMode() {
    var enabled = getDebugMode();
    document.body.classList.toggle('debug-enabled', enabled);
    var btn = document.getElementById('debug-toggle');
    if (btn) {
        btn.classList.toggle('active-toggle', enabled);
        btn.textContent = '\uD83D\uDD2C';
        btn.setAttribute('data-tooltip', enabled ? 'Debug score: ON' : 'Debug score: OFF');
    }
}
function toggleDebugMode() {
    localStorage.setItem('kanatka_debug_score', getDebugMode() ? '0' : '1');
    applyDebugMode();
}
function refreshPage() {
    location.reload();
}
function parseLightboxPayload(el) {
    try {
        return JSON.parse(el.getAttribute('data-lightbox-payload') || '{}');
    } catch (e) {
        return {};
    }
}
function getLightboxItems(group) {
    var nodes = document.querySelectorAll('.js-lightbox-trigger');
    var items = [];
    for (var i = 0; i < nodes.length; i++) {
        var node = nodes[i];
        if (node.getAttribute('data-lightbox-group') !== group) continue;
        items.push({
            index: parseInt(node.getAttribute('data-lightbox-index') || '0', 10),
            payload: parseLightboxPayload(node)
        });
    }
    items.sort(function(a, b) { return a.index - b.index; });
    var result = [];
    for (var j = 0; j < items.length; j++) result.push(items[j].payload);
    return result;
}
function openLightboxFromElement(el, evt) {
    if (evt && evt.target && evt.target.type === 'checkbox') return;
    if (evt) {
        evt.preventDefault();
        evt.stopPropagation();
    }
    var group = el.getAttribute('data-lightbox-group') || 'default';
    lightboxState.items = getLightboxItems(group);
    lightboxState.group = group;
    lightboxState.index = parseInt(el.getAttribute('data-lightbox-index') || '0', 10);
    lightboxState.active = true;
    renderLightbox();
}
function renderLightbox() {
    var overlay = document.getElementById('fullscreen');
    if (!overlay || !lightboxState.active || !lightboxState.items.length) return;
    var item = lightboxState.items[lightboxState.index] || {};
    overlay.querySelector('.lightbox-image').src = item.src || '';
    overlay.querySelector('.lightbox-title').textContent = item.title || '';
    overlay.querySelector('.lightbox-subtitle').textContent = item.subtitle || '';
    overlay.querySelector('.lightbox-counter').textContent =
        (lightboxState.index + 1) + ' / ' + lightboxState.items.length;
    overlay.querySelector('.lightbox-debug-panel').innerHTML = item.debug_html || '<div class="lightbox-debug-empty">Нет debug-данных.</div>';
    var scoreEl = overlay.querySelector('.lightbox-score');
    if (scoreEl) {
        while (scoreEl.firstChild) scoreEl.removeChild(scoreEl.firstChild);
        var s = typeof item.score === 'number' ? item.score : 0;
        if (s > 0) {
            var label = item.score_label || '';
            var sc = label ? '#7eb8f7' : (s >= 75 ? '#2ecc71' : s >= 50 ? '#f8d57f' : '#e74c3c');
            if (label) {
                var labelSpan = document.createElement('span');
                labelSpan.className = 'lightbox-score-denom';
                labelSpan.style.display = 'block';
                labelSpan.style.marginBottom = '2px';
                labelSpan.textContent = label;
                scoreEl.appendChild(labelSpan);
            }
            var valSpan = document.createElement('span');
            valSpan.className = 'lightbox-score-value';
            valSpan.style.color = sc;
            valSpan.textContent = s.toFixed(1);
            var denomSpan = document.createElement('span');
            denomSpan.className = 'lightbox-score-denom';
            denomSpan.textContent = '/ 100';
            scoreEl.appendChild(valSpan);
            scoreEl.appendChild(denomSpan);
        }
    }
    overlay.querySelector('.lightbox-nav.prev').disabled = lightboxState.index <= 0;
    overlay.querySelector('.lightbox-nav.next').disabled = lightboxState.index >= lightboxState.items.length - 1;
    overlay.classList.add('active');
}
function closeLightbox(evt) {
    if (evt && evt.target !== evt.currentTarget) return;
    lightboxState.active = false;
    var overlay = document.getElementById('fullscreen');
    if (overlay) overlay.classList.remove('active');
}
function moveLightbox(delta) {
    if (!lightboxState.active) return;
    var next = lightboxState.index + delta;
    if (next < 0 || next >= lightboxState.items.length) return;
    lightboxState.index = next;
    renderLightbox();
}
document.addEventListener('keydown', function(e) {
    if (!lightboxState.active) return;
    if (e.key === 'Escape') closeLightbox();
    if (e.key === 'ArrowLeft') moveLightbox(-1);
    if (e.key === 'ArrowRight') moveLightbox(1);
});
document.addEventListener('DOMContentLoaded', function() {
    applyDebugMode();
    updateDiskHealth();
    window.setInterval(updateDiskHealth, 30000);
    if ((window.KANATKA_PAGE_KEY === 'series-list' || window.KANATKA_PAGE_KEY === 'sheets') && window.KANATKA_MONITOR_ACTIVE) {
        window.setInterval(function() {
            fetch('/api/monitor', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({action: 'status'}),
                credentials: 'same-origin'
            }).then(function(resp) {
                return resp.json().catch(function() { return {}; });
            }).then(function(data) {
                if (!data || data.error) return;
                var changed = (
                    data.active !== window.KANATKA_MONITOR_ACTIVE ||
                    data.series_processed !== window.KANATKA_MONITOR_SERIES ||
                    data.last_activity !== window.KANATKA_MONITOR_LAST
                );
                if (changed) location.reload();
            }).catch(function() {});
        }, 3000);
    }
});

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

// Toast notification
function showToast(msg, type, duration) {
    var t = document.getElementById('toast');
    if (!t) return;
    t.textContent = msg;
    t.className = 'show' + (type === 'ok' ? ' toast-ok' : type === 'err' ? ' toast-err' : '');
    clearTimeout(window._toastTimer);
    window._toastTimer = setTimeout(function() { t.className = t.className.replace(' show','').replace('show',''); }, duration || 3000);
}

// README modal
function openReadme() {
    var m = document.getElementById('readme-modal');
    m.style.display = 'flex';
    var content = document.getElementById('readme-content');
    if (content.getAttribute('data-loaded')) return;
    fetch('/api/readme').then(function(r) { return r.text(); }).then(function(html) {
        content.innerHTML = html;
        content.setAttribute('data-loaded', '1');
    }).catch(function() { content.innerHTML = '<p>Не удалось загрузить инструкцию.</p>'; });
}
function closeReadme() {
    document.getElementById('readme-modal').style.display = 'none';
}
// (Escape handling for modals is unified in the cleanup section)

// Monitor control — v3 navbar button
function _setMonitorBtnState(active) {
    var btn = document.getElementById('monitor-btn-area');
    if (!btn) return;
    // Clear existing children safely
    while (btn.firstChild) btn.removeChild(btn.firstChild);
    if (active) {
        btn.className = 'monitor-btn stop';
        btn.setAttribute('onclick', "toggleMonitor('stop')");
        var dot = document.createElement('span');
        dot.className = 'pulse-dot';
        btn.appendChild(dot);
        btn.appendChild(document.createTextNode('\u041e\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442\u044c'));
    } else {
        btn.className = 'monitor-btn start';
        btn.setAttribute('onclick', "toggleMonitor('start')");
        btn.appendChild(document.createTextNode('\u25b6 \u0417\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u044c'));
    }
}

function toggleMonitor(action) {
    fetch('/api/monitor', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action: action}),
        credentials: 'same-origin'
    }).then(function(resp) {
        return resp.json().catch(function() { return {}; }).then(function(data) {
            if (action === 'start') {
                if (!resp.ok) { showToast('\u041e\u0448\u0438\u0431\u043a\u0430: ' + (data.error || 'HTTP ' + resp.status), 'err'); return; }
                if (!data.active) { showToast('\u041c\u043e\u043d\u0438\u0442\u043e\u0440\u0438\u043d\u0433 \u043d\u0435 \u0437\u0430\u043f\u0443\u0441\u0442\u0438\u043b\u0441\u044f: ' + (data.error || ''), 'err'); return; }
                _setMonitorBtnState(true);  // update button immediately
                // Launch inbox simulator and show test-mode notice
                fetch('/api/simulate', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'})
                    .then(function(r) { return r.json(); })
                    .then(function(d) {
                        if (d.status === 'ok') {
                            showToast('\u26a0\ufe0f \u0422\u0415\u0421\u0422\u041e\u0412\u042b\u0419 \u0420\u0415\u0416\u0418\u041c: \u0441\u0438\u043c\u0443\u043b\u044f\u0442\u043e\u0440 \u043f\u043e\u0434\u0430\u0451\u0442 \u0444\u043e\u0442\u043e \u0438\u0437 INBOX. \u0412 \u0440\u0430\u0431\u043e\u0447\u0435\u043c \u0440\u0435\u0436\u0438\u043c\u0435 \u0444\u043e\u0442\u043e \u043f\u043e\u0441\u0442\u0443\u043f\u0430\u044e\u0442 \u043e\u0442 \u043a\u0430\u043c\u0435\u0440\u044b \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438.', null, 5000);
                        } else if (d.status === 'inbox_empty') {
                            showToast('\u041c\u043e\u043d\u0438\u0442\u043e\u0440\u0438\u043d\u0433 \u0437\u0430\u043f\u0443\u0449\u0435\u043d. \u041f\u0430\u043f\u043a\u0430 INBOX \u043f\u0443\u0441\u0442\u0430 \u2014 \u0434\u043e\u0431\u0430\u0432\u044c\u0442\u0435 \u0444\u043e\u0442\u043e \u0432 INBOX \u0434\u043b\u044f \u0442\u0435\u0441\u0442\u0430.', 'err');
                        }
                        setTimeout(function() { location.reload(); }, d.status === 'ok' ? 5200 : 2200);
                    })
                    .catch(function() { location.reload(); });
                return;
            }
            location.reload();
        });
    })
    .catch(function(e) { showToast('\u041e\u0448\u0438\u0431\u043a\u0430: ' + e.message, 'err'); });
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

// Cleanup modal
function openCleanup() {
    document.getElementById('cleanup-modal').style.display = 'flex';
}
function closeCleanup() {
    document.getElementById('cleanup-modal').style.display = 'none';
}
// Escape closes any open modal
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        var modals = document.querySelectorAll('.modal-overlay');
        for (var i = 0; i < modals.length; i++) {
            if (modals[i].style.display === 'flex') modals[i].style.display = 'none';
        }
    }
});
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
            showToast('\u0423\u0434\u0430\u043b\u0435\u043d\u043e \u0444\u0430\u0439\u043b\u043e\u0432: ' + (data.deleted || 0), 'ok');
            setTimeout(function() { location.reload(); }, 1200);
        } else {
            showToast('\u041e\u0448\u0438\u0431\u043a\u0430: ' + (data.error || '\u043d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u0430\u044f'), 'err');
        }
    })
    .catch(function(e) { showToast('\u041e\u0448\u0438\u0431\u043a\u0430: ' + e.message, 'err'); });
}

// ZIP export modal
function openZipModal() {
    document.getElementById('zip-modal').style.display = 'flex';
}
function closeZipModal() {
    document.getElementById('zip-modal').style.display = 'none';
}
function toggleZipCustom() {
    var preset = document.querySelector('input[name="zip-preset"]:checked');
    var custom = document.getElementById('zip-custom-range');
    if (custom) custom.style.display = (preset && preset.value === 'custom') ? 'block' : 'none';
}
function runZipExport() {
    var preset = document.querySelector('input[name="zip-preset"]:checked');
    if (!preset) return;
    var dateFrom = '', dateTo = '';
    var today = new Date().toISOString().slice(0, 10);
    if (preset.value === 'today') {
        dateFrom = today; dateTo = today;
    } else if (preset.value === 'week') {
        var d = new Date(); d.setDate(d.getDate() - 7);
        dateFrom = d.toISOString().slice(0, 10); dateTo = today;
    } else if (preset.value === 'custom') {
        dateFrom = document.getElementById('zip-from').value;
        dateTo = document.getElementById('zip-to').value;
    }
    var btn = document.getElementById('zip-run-btn');
    btn.disabled = true; btn.textContent = '\u0421\u043e\u0437\u0434\u0430\u0451\u043c...';
    fetch('/api/export-zip', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({preset: preset.value, date_from: dateFrom, date_to: dateTo}),
        credentials: 'same-origin'
    }).then(function(r) { return r.json(); })
    .then(function(data) {
        btn.disabled = false; btn.textContent = '\u0421\u043e\u0437\u0434\u0430\u0442\u044c ZIP';
        if (data.status === 'ok') {
            closeZipModal();
            showToast('ZIP \u0441\u043e\u0445\u0440\u0430\u043d\u0451\u043d: ' + data.filename, 'ok');
        } else {
            showToast('\u041e\u0448\u0438\u0431\u043a\u0430: ' + (data.error || '\u043d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u0430\u044f'), 'err');
        }
    })
    .catch(function(e) {
        btn.disabled = false; btn.textContent = '\u0421\u043e\u0437\u0434\u0430\u0442\u044c ZIP';
        showToast('\u041e\u0448\u0438\u0431\u043a\u0430: ' + e.message, 'err');
    });
}

// Disk health polling — textContent only, no user-controlled data
function updateDiskHealth() {
    fetch('/api/health', {credentials: 'same-origin'})
    .then(function(r) { return r.json().catch(function() { return {}; }); })
    .then(function(data) {
        var iconEl = document.getElementById('disk-indicator-icon');
        var textEl = document.getElementById('disk-indicator-text');
        if (!iconEl || !textEl) return;
        var freeText = data.free_gb != null ? (data.free_gb + '\u00a0\u0413\u0411') : '...';
        if (data.status === 'critical') {
            iconEl.textContent = '\uD83D\uDD34';
            textEl.textContent = freeText;
            iconEl.parentElement.style.color = '#e74c3c';
        } else if (data.status === 'warning') {
            iconEl.textContent = '\u26A0';
            textEl.textContent = freeText;
            iconEl.parentElement.style.color = '#f39c12';
        } else {
            iconEl.textContent = '\uD83D\uDCBE';
            textEl.textContent = freeText;
            iconEl.parentElement.style.color = '';
        }
    }).catch(function() {});
}
"""


def _page(title: str, body: str, stats: str = "", active_nav: str = "series",
          show_view_switcher: bool = False, page_key: str = "series") -> str:
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

    # Monitor state for navbar button
    mon = _MonitorState.status_dict()
    _cfg = getattr(SeriesBrowserHandler, "config", None) or {}
    _print_cfg = _cfg.get("print", {})
    _debug_default = "true" if _cfg.get("output", {}).get("show_score_badge", True) else "false"
    _monitor_active = "true" if mon["active"] else "false"
    _monitor_series = int(mon.get("series_processed", 0))
    _monitor_last = json.dumps(mon.get("last_activity", ""), ensure_ascii=False)

    # Monitor button in navbar (always visible on all pages)
    if mon["active"]:
        monitor_btn_html = (
            '<button id="monitor-btn-area" class="monitor-btn stop" onclick="toggleMonitor(\'stop\')">'
            '<span class="pulse-dot"></span>'
            f'Серий: {_monitor_series} \u00b7 Остановить'
            '</button>'
        )
    else:
        monitor_btn_html = (
            '<button id="monitor-btn-area" class="monitor-btn start" onclick="toggleMonitor(\'start\')">'
            '&#9654; Запустить'
            '</button>'
        )

    # Stats badge (only on series pages)
    stats_html = ""
    if stats:
        stats_html = f'<span class="stats-badge">{stats}</span>'

    # Ambiguous indicator for stats
    ambiguous_count = _count_ambiguous_series()
    if ambiguous_count > 0:
        stats_html += (
            f'<a href="/?filter=ambiguous" style="font-size:13px; '
            f'color:#f39c12; font-weight:600; text-decoration:none; white-space:nowrap">'
            f'&#9888; {ambiguous_count}'
            f'</a>'
        )

    return (
        '<!DOCTYPE html>\n'
        '<html lang="ru"><head>\n'
        '<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{title}</title>\n'
        f'<style>{_CSS}</style>\n'
        '</head><body>\n'
        '<nav class="navbar">\n'
        '  <a href="/" class="brand"><span>&#127935;</span> Kanatka</a>\n'
        '  <div class="page-switcher">\n'
        f'    <a href="/" class="{nav_cls("series")}">Серии</a>\n'
        f'    <a href="/sheets" class="{nav_cls("sheets")}">Листы</a>\n'
        '  </div>\n'
        '  <div class="nav-divider"></div>\n'
        '  <div class="action-buttons">\n'
        '    <button class="action-btn" data-tooltip="Обновить" onclick="refreshPage(); return false;">&#x21BB;</button>\n'
        '    <button class="action-btn" data-tooltip="Архив (ZIP)" onclick="openZipModal(); return false;">&#x1F4E6;</button>\n'
        '    <button id="debug-toggle" class="action-btn" data-tooltip="Debug score" onclick="toggleDebugMode(); return false;">&#x1F50D;</button>\n'
        '    <button class="action-btn danger" data-tooltip="Очистка" onclick="openCleanup(); return false;">&#x2716;</button>\n'
        '    <button class="action-btn" data-tooltip="Инструкция" onclick="openReadme(); return false;">&#x2753;</button>\n'
        '  </div>\n'
        '  <div class="nav-divider"></div>\n'
        f'  {monitor_btn_html}\n'
        '  <div class="nav-spacer"></div>\n'
        '  <div class="nav-right">\n'
        f'    {view_switcher_html}\n'
        '    <div class="disk-indicator">'
        '<span class="icon" id="disk-indicator-icon">&#128190;</span>'
        '<span class="disk-text" id="disk-indicator-text">...</span></div>\n'
        f'    {stats_html}\n'
        f'    <a href="/settings" class="settings-btn" title="Настройки">&#9881;</a>\n'
        '  </div>\n'
        '</nav>\n'
        f'<div class="container">{body}</div>\n'
        '<div id="cleanup-modal" class="modal-overlay" onclick="if(event.target===this)closeCleanup()">'
        '<div class="modal-content" style="max-width:420px">'
        '<div class="modal-header"><h3>Очистка рабочих папок</h3>'
        '<button class="modal-close" onclick="closeCleanup()">&times;</button></div>'
        '<div class="modal-body">'
        '<p style="color:#666; font-size:13px; margin-bottom:16px">Выберите папки для очистки. Файлы будут удалены безвозвратно. '
        'Карточки на вкладке «Серии» строятся по отчётам из logs, поэтому без последнего пункта история серий останется видимой.</p>'
        '<div style="display:flex; flex-direction:column; gap:10px">'
        '<label style="cursor:pointer"><input type="checkbox" name="incoming"> Входящие фото (ожидают обработки)</label>'
        '<label style="cursor:pointer"><input type="checkbox" name="selected"> Лучшие фото (отобранные)</label>'
        '<label style="cursor:pointer"><input type="checkbox" name="rejected"> Худшие фото серий</label>'
        '<label style="cursor:pointer"><input type="checkbox" name="discarded"> Пустые кресла</label>'
        '<label style="cursor:pointer"><input type="checkbox" name="ambiguous"> Спорные серии</label>'
        '<label style="cursor:pointer"><input type="checkbox" name="sheets"> Печатные листы</label>'
        '<label style="cursor:pointer"><input type="checkbox" name="archive"> Архив обработанных</label>'
        '<label style="cursor:pointer"><input type="checkbox" name="logs"> Отчёты серий, логи, аннотации (убирает карточки серий)</label>'
        '<hr style="margin:8px 0">'
        '<label style="cursor:pointer; color:#e74c3c; font-weight:700"><input type="checkbox" onchange="toggleCleanupAll(this)"> Выбрать всё</label>'
        '</div>'
        '<div style="display:flex; gap:12px; margin-top:20px; justify-content:flex-end">'
        '<button onclick="closeCleanup()" style="padding:8px 20px; border:1px solid #ddd; border-radius:8px; background:#fff; cursor:pointer">Отмена</button>'
        '<button onclick="runCleanup()" style="padding:8px 20px; border:none; border-radius:8px; background:#e74c3c; color:#fff; cursor:pointer; font-weight:600">Удалить</button>'
        '</div></div></div></div>\n'
        '<div id="toast" role="status" aria-live="polite"></div>\n'
        '<div id="zip-modal" class="modal-overlay" onclick="if(event.target===this)closeZipModal()">'
        '<div class="modal-content" style="max-width:400px">'
        '<div class="modal-header"><h3>Архив ZIP</h3>'
        '<button class="modal-close" onclick="closeZipModal()">&times;</button></div>'
        '<div class="modal-body">'
        '<p style="color:#666; font-size:13px; margin-bottom:16px">ZIP с лучшими фото и листами будет сохранён на Рабочий стол.</p>'
        '<div style="display:flex; flex-direction:column; gap:10px; margin-bottom:16px">'
        '<label style="cursor:pointer"><input type="radio" name="zip-preset" value="all" checked onchange="toggleZipCustom()"> Всё</label>'
        '<label style="cursor:pointer"><input type="radio" name="zip-preset" value="today" onchange="toggleZipCustom()"> Сегодня</label>'
        '<label style="cursor:pointer"><input type="radio" name="zip-preset" value="week" onchange="toggleZipCustom()"> Эта неделя</label>'
        '<label style="cursor:pointer"><input type="radio" name="zip-preset" value="custom" onchange="toggleZipCustom()"> Свой диапазон</label>'
        '</div>'
        '<div id="zip-custom-range" style="display:none; margin-bottom:16px">'
        '<label style="font-size:13px">С&nbsp;<input type="date" id="zip-from">'
        '&nbsp;по&nbsp;<input type="date" id="zip-to"></label>'
        '</div>'
        '<div style="display:flex; gap:12px; justify-content:flex-end">'
        '<button onclick="closeZipModal()" style="padding:8px 20px; border:1px solid #ddd; border-radius:8px; background:#fff; cursor:pointer">Отмена</button>'
        '<button id="zip-run-btn" onclick="runZipExport()" style="padding:8px 20px; border:none; border-radius:8px; background:#3498db; color:#fff; cursor:pointer; font-weight:600">Создать ZIP</button>'
        '</div></div></div></div>\n'
        '<div id="readme-modal" class="modal-overlay" onclick="if(event.target===this)closeReadme()">'
        '<div class="modal-content" style="max-width:720px; max-height:82vh; display:flex; flex-direction:column">'
        '<div class="modal-header"><h3>Инструкция</h3>'
        '<button class="modal-close" onclick="closeReadme()">&times;</button></div>'
        '<div class="modal-body" style="overflow-y:auto; flex:1; padding-bottom:0">'
        '<div id="readme-content" style="font-size:14px; line-height:1.6; color:#333">'
        '<p style="color:#aaa">Загрузка...</p>'
        '</div></div>'
        '<div style="padding:16px 28px; flex-shrink:0; text-align:right">'
        '<button onclick="closeReadme()" style="padding:8px 24px; border:none; border-radius:8px; background:#1a1a2e; color:#fff; cursor:pointer; font-weight:600">Закрыть</button>'
        '</div></div></div>\n'
        '<div id="fullscreen" class="fullscreen-overlay" onclick="closeLightbox(event)">'
        '<div class="lightbox-shell">'
        '<div class="lightbox-main">'
        '<button class="lightbox-close" onclick="closeLightbox()">&times;</button>'
        '<button class="lightbox-nav prev" onclick="moveLightbox(-1)">&lsaquo;</button>'
        '<img class="lightbox-image" src="" alt="">'
        '<button class="lightbox-nav next" onclick="moveLightbox(1)">&rsaquo;</button>'
        '</div>'
        '<aside class="lightbox-side">'
        '<div class="lightbox-title"></div>'
        '<div class="lightbox-subtitle"></div>'
        '<div class="lightbox-score"></div>'
        '<div class="lightbox-counter"></div>'
        '<div class="lightbox-debug-panel"></div>'
        '<div class="lightbox-hint">Esc — закрыть. Стрелки влево/вправо — перейти к соседнему кадру в текущей серии.</div>'
        '</aside>'
        '</div></div>\n'
        f'<script>window.KANATKA_PAGE_KEY = {json.dumps(page_key, ensure_ascii=False)};</script>\n'
        f'<script>window.KANATKA_MONITOR_ACTIVE = {_monitor_active}; window.KANATKA_MONITOR_SERIES = {_monitor_series}; window.KANATKA_MONITOR_LAST = {_monitor_last};</script>\n'
        f'<script>window.KANATKA_DEBUG_DEFAULT = {_debug_default};</script>\n'
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


def _render_series_card(series: dict, config: dict, history_mode: bool = False) -> str:
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

    thumb_path = _resolve_series_card_thumb(series, config)
    if thumb_path:
        thumb_html = (
            f'<img class="series-thumb" src="/photo?path={quote(str(thumb_path), safe="")}&amp;max_side=400" '
            f'alt="{name}" loading="lazy" onerror="this.style.display=\'none\'">'
        )
    else:
        thumb_html = (
            '<div class="series-thumb" style="display:flex; align-items:center; justify-content:center; '
            'background:#eef1f5; color:#6b7280; font-weight:600; min-height:220px">Файлы очищены</div>'
        )

    action_html = ""
    if not history_mode:
        action_html = (
            (f'<button onclick="confirmAmbiguous(\'{name}\')" '
               f'style="font-size:12px; padding:5px 12px; background:#27ae60; color:#fff; border:none; cursor:pointer; border-radius:8px; font-weight:700">'
               f'Подтвердить</button>'
               if status == "ambiguous_manual_review" else "")
        )

    return (
        '<div class="series-card">'
        f'<a href="/series/{name}">'
        f'{thumb_html}'
        '<div class="series-info">'
        f'<div class="series-name">{name} {score_html}</div>'
        f'<div class="series-meta">{badge} &middot; {photo_count} фото'
        + (' &middot; История' if history_mode else '')
        + '</div>'
        '</div></a>'
        f'<div style="padding:0 16px 12px; display:flex; gap:6px">'
        + action_html
        + '</div>'
        '</div>'
    )


def _render_series_list(all_series: list[dict], config: dict, page: int = 1, filter_status: str = "") -> str:
    live_series, history_series = _series_visibility(all_series, config)
    selected_count = sum(1 for s in live_series if s.get("status") == "selected")
    empty_count = sum(1 for s in live_series if s.get("status") == "discarded_empty")
    ambiguous_count = sum(1 for s in live_series if s.get("status") == "ambiguous_manual_review")
    stats = (
        f"Рабочие: {len(live_series)} | История: {len(history_series)} | "
        f"Выбрано: {selected_count} | Спорных: {ambiguous_count} | Пустых: {empty_count}"
    )

    history_mode = filter_status == "history"
    if filter_status == "ambiguous":
        display_series = [s for s in live_series if s.get("status") == "ambiguous_manual_review"]
    elif history_mode:
        display_series = history_series
    else:
        display_series = live_series

    # Pagination
    filtered_total = len(display_series)
    total_pages = max(1, (filtered_total + _SERIES_PER_PAGE - 1) // _SERIES_PER_PAGE)
    page = max(1, min(page, total_pages))
    start = (page - 1) * _SERIES_PER_PAGE
    end = min(start + _SERIES_PER_PAGE, filtered_total)
    page_series = display_series[start:end]

    cards = [_render_series_card(s, config, history_mode=history_mode) for s in page_series]

    # Filter tabs
    filter_param = f"&filter={filter_status}" if filter_status else ""
    live_cls = "" if filter_status else "active"
    amb_cls = "active" if filter_status == "ambiguous" else ""
    history_cls = "active" if history_mode else ""
    filter_tabs = (
        '<div style="margin-bottom:12px; display:flex; gap:8px">'
        f'<a href="/" class="page-btn {live_cls}" style="text-decoration:none">Рабочие ({len(live_series)})</a>'
        f'<a href="/?filter=ambiguous" class="page-btn {amb_cls}" style="text-decoration:none; '
        f'color:{("#f39c12" if ambiguous_count else "#999")}">'
        f'&#9888; Спорные ({ambiguous_count})</a>'
        f'<a href="/?filter=history" class="page-btn {history_cls}" style="text-decoration:none">'
        f'История ({len(history_series)})</a>'
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

    # Monitor bar removed in v3 — control is now in navbar
    monitor_bar = ""

    empty_state = ""
    if not cards:
        empty_label = "История пуста." if history_mode else "В рабочем окне пока нет серий."
        if history_mode:
            empty_hint = "Здесь собраны только серии, для которых уже очищены рабочие файлы."
        elif history_series:
            empty_hint = (
                f"Запустите мониторинг и симулятор камеры — новые серии появятся здесь. "
                f"Ранее обработанные серии ({len(history_series)} шт.) доступны во вкладке «История»."
            )
        else:
            empty_hint = "Запустите мониторинг входящей папки и запустите симулятор камеры."
        empty_state = (
            '<div style="background:#fff; border-radius:14px; padding:22px 24px; color:#55606f; '
            'box-shadow:0 2px 8px rgba(0,0,0,0.05); margin-bottom:16px">'
            f'<div style="font-weight:700; color:#22313f; margin-bottom:6px">{empty_label}</div>'
            f'<div style="font-size:14px">{empty_hint}</div>'
            '</div>'
        )

    body = (
        monitor_bar
        + filter_tabs
        + empty_state
        + '<div class="series-grid view-medium">'
        + "".join(cards)
        + '</div>'
        + pagination
    )
    return _page("Kanatka — Серии", body, stats, show_view_switcher=True, page_key="series-list")


def _render_series_detail(series: dict, selected_dir: Path, config: dict) -> str:
    name = series.get("series", "?")
    photos = series.get("photos", [])
    selected_file = series.get("selected_file", "")
    existing_selected = (
        {p.name for p in selected_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"}}
        if selected_dir.exists() else set()
    )
    live_series = _series_has_live_assets(series, config)

    breadcrumb = (
        '<div class="breadcrumb">'
        '<a href="/">&larr; Все серии</a> / ' + name
        + '</div>'
    )

    cards = []
    group_name = f"series-{name}"
    for index, photo in enumerate(photos):
        fname = photo.get("file_name", "?")
        fpath = photo.get("file_path", "")
        score = photo.get("score", 0)
        present = photo.get("subject_present", False)
        fallback = photo.get("person_fallback", False)
        actual_path = _find_existing_photo_for_series(photo, name, config, selected_file=selected_file)
        rescue_source = _find_rescue_source(photo, config)

        score_val = score if isinstance(score, (int, float)) else 0
        detect_info = _detect_label(present, fallback)
        inline_debug_html = _build_inline_debug_html(photo)

        rescue_name = f"{name}_{fname}"
        already_rescued = rescue_name in existing_selected or selected_file == rescue_name
        if already_rescued:
            rescue_html = '<span class="rescued-badge">Уже выбрано</span>'
        elif rescue_source is None:
            rescue_html = '<span class="rescued-badge" style="background:#bdc3c7">Исходник очищен</span>'
        else:
            form_id = f"rescue_{fname.replace('.', '_')}"
            rescue_html = (
                f'<form id="{form_id}" method="POST" action="/rescue" style="display:inline">'
                f'<input type="hidden" name="path" value="{rescue_source}">'
                f'<input type="hidden" name="series" value="{name}">'
                f'<input type="hidden" name="file_name" value="{fname}">'
                f'<button type="button" class="rescue-btn" onclick="confirmRescue(\'{form_id}\', \'{fname}\')">Спасти фото</button>'
                '</form>'
            )

        if actual_path is not None:
            thumb_src = f'/photo?path={quote(str(actual_path), safe="")}&amp;max_side=400'
            full_src = f'/photo?path={quote(str(actual_path), safe="")}&amp;max_side=2200'
            payload = _build_lightbox_payload_attr(
                full_src,
                fname,
                f"{name} · {detect_info}",
                _build_lightbox_debug_html(photo),
                score=float(score_val),
            )
            thumb_html = (
                f'<img class="photo-thumb js-lightbox-trigger" src="{thumb_src}" alt="{fname}" loading="lazy"'
                f' data-lightbox-group="{group_name}" data-lightbox-index="{index}"'
                f' data-lightbox-payload="{payload}"'
                f' onclick="openLightboxFromElement(this, event)"'
                " onerror=\"this.style.display='none'\">"
            )
        else:
            thumb_html = (
                '<div class="photo-thumb" style="display:flex; align-items:center; justify-content:center; '
                'background:#eef1f5; color:#6b7280; font-weight:600; min-height:220px">Файл очищен</div>'
            )

        cards.append(
            '<div class="photo-card">'
            f'{thumb_html}'
            '<div class="photo-info">'
            f'<div class="photo-name">{fname}</div>'
            f'<div class="photo-score">Score: {_score_span(score_val)} &middot; {detect_info}</div>'
            f'{inline_debug_html}'
            f'{rescue_html}'
            '</div></div>'
        )

    body = breadcrumb + f'<h2 style="margin-bottom:16px">{name} — {len(photos)} фото</h2>'
    if not live_series:
        body += (
            '<div style="background:#fff4db; color:#7d5b00; border:1px solid #f0d28a; border-radius:12px; '
            'padding:14px 16px; margin-bottom:16px">'
            '<b>История серии.</b> Рабочие файлы уже очищены, поэтому просмотр и rescue ограничены.'
            '</div>'
        )
    body += '<div class="photo-grid">' + "".join(cards) + '</div>'
    return _page(f"Kanatka — {name}", body)


# ---------------------------------------------------------------------------
# Settings page
# ---------------------------------------------------------------------------

# Each setting: (config_section, config_key, label, hint, input_type, extra)
# input_type: "range", "number", "checkbox", "text"
# extra: dict with min, max, step for range/number
_SETTINGS_SCHEMA: list[tuple[str, str, list[tuple]]] = [
    (
        "Детекция серий",
        "Как программа режет непрерывный поток входящих файлов на отдельные серии.",
        [
            ("series_detection", "max_gap_seconds", "Макс. разрыв внутри серии",
             "Если соседние кадры отличаются по времени создания не больше этого значения — это одна серия.",
             "range", {"min": 0.1, "max": 10, "step": 0.1}),
            ("series_detection", "cooldown_seconds", "Ожидание тишины перед разбором",
             "Сколько ждать после последнего нового файла, прежде чем разбирать накопившуюся очередь.",
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
        "Спорные серии",
        "Порог, при котором автоматический выбор считается неуверенным и серия помечается для ручной проверки.",
        [
            ("decision", "manual_review_enabled", "Включить manual review",
             "Если выключить, программа не будет помечать близкие по score серии как спорные.",
             "checkbox", {}),
            ("decision", "delta_score", "Мин. разница score",
             "Если разница между лучшим и вторым кадром меньше этого порога, серия будет отмечена как спорная.",
             "range", {"min": 0, "max": 25, "step": 0.5}),
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
        "Рабочие папки",
        "Пути к рабочим директориям. Можно указать абсолютные пути или относительные (от папки программы).",
        [
            ("paths", "input_folder", "Входящие фото",
             "Папка, куда камера складывает снимки. Мониторинг следит за этой папкой.",
             "text", {}),
            ("paths", "output_selected", "Лучшие фото",
             "Сюда сохраняются отобранные фото (по одному на серию).",
             "text", {}),
            ("paths", "output_sheets", "Печатные листы",
             "Сюда сохраняются собранные листы для печати.",
             "text", {}),
            ("paths", "output_discarded", "Пустые кресла",
             "Сюда перемещаются фото серий без людей.",
             "text", {}),
            ("paths", "output_rejected", "Отклонённые фото",
             "Сюда перемещаются фото, проигравшие при отборе.",
             "text", {}),
            ("paths", "output_archive", "Архив",
             "Сюда перемещаются обработанные фото после сборки листа.",
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
    (
        "Мониторинг диска",
        "Пороги предупреждений о нехватке свободного места на диске.",
        [
            ("health", "min_free_gb", "Предупреждение (ГБ)",
             "Если свободного места меньше этого значения — жёлтый индикатор в навбаре.",
             "range", {"min": 0.1, "max": 10.0, "step": 0.1}),
            ("health", "critical_free_gb", "Критично (ГБ)",
             "Если свободного места меньше этого значения — красный индикатор и блокировка запуска мониторинга.",
             "range", {"min": 0.1, "max": 5.0, "step": 0.1}),
        ],
    ),
    (
        "Логирование",
        "Управление записью логов на диск. Отключение экономит ресурсы SSD.",
        [
            ("logging", "log_to_file", "Записывать лог в файл",
             "Если выключено — логи выводятся только в консоль. Изменение вступает в силу после перезапуска программы.",
             "checkbox", {}),
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


def _build_sheet_debug_html(sheet_path: Path) -> tuple[str, float]:
    """Load sheet sidecar JSON and build a score grid for the lightbox sidebar.

    Returns (debug_html, avg_score). avg_score is 0.0 if no metadata found.
    """
    meta_path = sheet_path.with_suffix(".json")
    if not meta_path.exists():
        return "", 0.0
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return "", 0.0

    photos = meta.get("photos", [])
    columns = int(meta.get("columns", 2))
    if not photos:
        return "", 0.0

    scores = [float(p["score"]) for p in photos if isinstance(p.get("score"), (int, float))]
    avg = sum(scores) / len(scores) if scores else 0.0

    def score_color(s: float) -> str:
        return "#2ecc71" if s >= 75 else "#f8d57f" if s >= 50 else "#e74c3c"

    cells = []
    for p in photos:
        series = escape(str(p.get("series", "—")))
        s = p.get("score")
        if isinstance(s, (int, float)):
            s_f = float(s)
            color = score_color(s_f)
            score_html = f'<span style="font-size:20px; font-weight:800; color:{color}">{s_f:.1f}</span>'
        else:
            score_html = '<span style="color:#8b97aa; font-size:14px">—</span>'
        cells.append(
            f'<div style="background:rgba(255,255,255,0.06); border-radius:8px; padding:8px 6px; text-align:center;">'
            f'<div style="font-size:11px; color:#8b97aa; margin-bottom:3px">{series}</div>'
            f'{score_html}'
            f'</div>'
        )

    grid_html = (
        f'<div style="display:grid; grid-template-columns:repeat({columns}, 1fr); gap:6px;">'
        + "".join(cells)
        + "</div>"
    )
    return grid_html, round(avg, 1)


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
        return _page("Kanatka — Листы", body, active_nav="sheets", page_key="sheets")

    cards = []
    for index, sf in enumerate(sheet_files):
        mtime = sf.stat().st_mtime
        from datetime import datetime as _dt
        time_str = _dt.fromtimestamp(mtime).strftime("%d.%m.%Y %H:%M")
        size_kb = sf.stat().st_size // 1024
        thumb_url = f"/photo?path={sf.resolve()}&max_side=600"
        full_url = f"/photo?path={sf.resolve()}&max_side=3600"
        sheet_debug_html, avg_score = _build_sheet_debug_html(sf)
        payload = _build_lightbox_payload_attr(
            full_url,
            sf.name,
            f"{time_str} · {size_kb} KB",
            debug_html=sheet_debug_html,
            score=avg_score,
            score_label="Средняя оценка по листу" if avg_score > 0 else "",
        )
        card = (
            '<div class="sheet-card">'
            f'<img src="{thumb_url}" class="js-lightbox-trigger" '
            f'data-lightbox-group="sheets-gallery" data-lightbox-index="{index}" '
            f'data-lightbox-payload="{payload}" onclick="openLightboxFromElement(this, event)" '
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
        if (d.status === 'ok') { showToast('Лист отправлен на печать', 'ok'); }
        else { showToast('Ошибка: ' + (d.error || 'неизвестная'), 'err'); }
    });
}
"""

    body = (
        f'<h2>Собранные листы '
        f'<span style="font-size:14px; color:{mode_color}; font-weight:700">{mode_label}</span>'
        f'</h2>'
        '<p style="margin-top:0; color:#666; font-size:14px">'
        'Клик по превью открывает лист в полном размере. Так удобнее проверять score overlay и финальную компоновку.'
        '</p>'
        f'<div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(280px, 1fr)); gap:16px">'
        + "".join(cards)
        + '</div>'
        f'<script>{js}</script>'
    )
    return _page("Kanatka — Листы", body, active_nav="sheets", page_key="sheets")


def _render_settings(config: dict) -> str:
    """Render the engineer settings page with all tunable parameters."""
    groups = []
    sidebar_links = []
    for idx, (group_title, group_desc, settings) in enumerate(_SETTINGS_SCHEMA):
        section_id = f"section-{idx}"
        sidebar_links.append(f'<a href="#{section_id}" onclick="highlightSidebarLink(this)">{group_title}</a>')
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
            f'<div class="settings-group" id="{section_id}">'
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

    sidebar_links.append('<a href="#change-password" onclick="highlightSidebarLink(this)">Пароль</a>')
    sidebar_html = (
        '<aside class="settings-sidebar"><nav>'
        + "".join(sidebar_links)
        + '</nav></aside>'
    )

    sidebar_js = r"""
function highlightSidebarLink(el) {
    var links = document.querySelectorAll('.settings-sidebar a');
    for (var i = 0; i < links.length; i++) links[i].classList.remove('active');
    el.classList.add('active');
}
(function() {
    var groups = document.querySelectorAll('.settings-group, .change-pw-section');
    var links = document.querySelectorAll('.settings-sidebar a');
    if (!groups.length || !links.length) return;
    var observer = new IntersectionObserver(function(entries) {
        entries.forEach(function(entry) {
            if (entry.isIntersecting) {
                var id = entry.target.id;
                for (var i = 0; i < links.length; i++) {
                    links[i].classList.toggle('active', links[i].getAttribute('href') === '#' + id);
                }
            }
        });
    }, { rootMargin: '-80px 0px -60% 0px', threshold: 0 });
    for (var i = 0; i < groups.length; i++) observer.observe(groups[i]);
})();
"""

    body = (
        '<div class="settings-page">'
        '<h2 style="margin-bottom:8px">Настройки инженера ' + logout_btn + '</h2>'
        + first_login_banner +
        '<p style="color:#666; margin-bottom:20px; font-size:14px">'
        'Параметры для полевой настройки программы. Изменения сохраняются в config.json.</p>'
        '<div class="settings-layout">'
        + sidebar_html
        + '<div class="settings-main">'
        + "".join(groups)
        + '<div class="save-bar">'
        '<span id="save-msg" class="save-msg"></span>'
        '<button onclick="saveSettings()">Сохранить настройки</button>'
        '</div>'
        + change_pw_html
        + '</div></div></div>'
        f'<script>{save_js}\n{scroll_js}\n{sidebar_js}</script>'
    )
    return _page("Kanatka — Настройки", body, active_nav="settings")


def _md_to_html(text: str) -> str:
    """Convert minimal markdown to HTML for the README modal."""
    import re as _re
    lines = text.split("\n")
    result: list[str] = []
    in_ul = False
    in_code = False
    for line in lines:
        if line.startswith("```"):
            if in_ul:
                result.append("</ul>")
                in_ul = False
            in_code = not in_code
            result.append("<pre>" if in_code else "</pre>")
            continue
        if in_code:
            result.append(line.replace("&", "&amp;").replace("<", "&lt;"))
            continue
        if line.startswith("### "):
            if in_ul:
                result.append("</ul>")
                in_ul = False
            result.append(f"<h4 style='margin:14px 0 4px'>{line[4:]}</h4>")
        elif line.startswith("## "):
            if in_ul:
                result.append("</ul>")
                in_ul = False
            result.append(f"<h3 style='margin:18px 0 6px; border-bottom:1px solid #eee; padding-bottom:4px'>{line[3:]}</h3>")
        elif line.startswith("# "):
            if in_ul:
                result.append("</ul>")
                in_ul = False
            result.append(f"<h2 style='margin:0 0 12px'>{line[2:]}</h2>")
        elif line.startswith(("- ", "* ")):
            if not in_ul:
                result.append("<ul style='margin:6px 0; padding-left:20px'>")
                in_ul = True
            content = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line[2:])
            content = _re.sub(r"`(.+?)`", r"<code style='background:#f4f4f4;padding:1px 4px;border-radius:3px'>\1</code>", content)
            result.append(f"<li style='margin:3px 0'>{content}</li>")
        elif line.strip() == "":
            if in_ul:
                result.append("</ul>")
                in_ul = False
            result.append("<br>")
        else:
            if in_ul:
                result.append("</ul>")
                in_ul = False
            content = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
            content = _re.sub(r"`(.+?)`", r"<code style='background:#f4f4f4;padding:1px 4px;border-radius:3px'>\1</code>", content)
            result.append(f"<p style='margin:4px 0'>{content}</p>")
    if in_ul:
        result.append("</ul>")
    return "\n".join(result)


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
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        encoded = html.encode("utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_jpeg(self, data: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
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

    def _handle_export_zip(self, body: str) -> None:
        """Create a ZIP archive of selected photos and sheets."""
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            data = {}
        date_from = data.get("date_from") or None
        date_to = data.get("date_to") or None
        try:
            from export_utils import create_results_zip
            zip_path = create_results_zip(self.config, date_from=date_from, date_to=date_to)
            self._send_json({"status": "ok", "filename": zip_path.name})
        except ValueError as exc:
            self._send_json({"error": str(exc)}, 400)
        except Exception as exc:
            self._send_json({"error": str(exc)}, 500)

    def _handle_monitor(self, body: str) -> None:
        """Start or stop INBOX monitoring."""
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"error": "invalid JSON"}, 400)
            return

        action = data.get("action", "")
        if action == "start":
            try:
                from watcher import check_disk_space
                disk = check_disk_space(self.config)
                if disk["status"] == "critical":
                    self._send_json({
                        "error": f"Критически мало места на диске: {disk['free_gb']} ГБ. Мониторинг не запущен.",
                        "disk": disk,
                    }, 400)
                    return
            except Exception:
                pass
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
        # Re-resolve relative paths against PROJECT_ROOT (same as load_config)
        from config_utils import _resolve_path
        for key, value in self.config.get("paths", {}).items():
            if isinstance(value, str):
                self.config["paths"][key] = _resolve_path(value)
        ensure_runtime_directories(self.config)
        self._send_json({"status": "ok"})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        params = parse_qs(parsed.query)

        if path == "/":
            series = self._get_series()
            page = int(params.get("page", ["1"])[0])
            filter_status = params.get("filter", [""])[0]
            html = _render_series_list(series, self.config, page=page, filter_status=filter_status)
            self._send_html(html)

        elif path.startswith("/series/"):
            series_name = path.split("/series/", 1)[1]
            series = self._get_series()
            found = next((s for s in series if s.get("series") == series_name), None)
            if found:
                selected_dir = Path(self.config["paths"]["output_selected"])
                html = _render_series_detail(found, selected_dir, self.config)
                self._send_html(html)
            else:
                self._send_html("<h1>Серия не найдена</h1>", 404)

        elif path == "/api/health":
            try:
                from watcher import check_disk_space
                disk_data = check_disk_space(self.config)
            except Exception:
                disk_data = {"free_gb": None, "status": "ok"}
            self._send_json(disk_data)

        elif path == "/api/readme":
            from config_utils import get_project_root
            _root = get_project_root()
            _candidates = [
                _root / "docs" / "user_testing_guide.md",
                _root / "README.md",
            ]
            _md_text = ""
            for _p in _candidates:
                if _p.exists():
                    try:
                        _md_text = _p.read_text(encoding="utf-8")
                    except OSError:
                        pass
                    break
            _html_content = _md_to_html(_md_text) if _md_text else "<p>Файл инструкции не найден.</p>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(_html_content.encode("utf-8"))

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
            if real_path.exists() and real_path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
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

        if parsed.path == "/api/export-zip":
            self._handle_export_zip(body)
            return

        if parsed.path == "/api/simulate":
            from config_utils import get_project_root
            inbox_dir = Path(self.config["paths"]["test_photos_folder"])
            if not inbox_dir.is_absolute():
                inbox_dir = get_project_root() / inbox_dir
            if _SimulatorState.is_active():
                self._send_json({"status": "already_running"})
                return
            has_images = inbox_dir.exists() and any(
                f for ext in ("*.jpg", "*.jpeg", "*.png") for f in inbox_dir.glob(ext)
            )
            if not has_images:
                self._send_json({"status": "inbox_empty"})
                return
            _SimulatorState.thread = threading.Thread(
                target=_run_inbox_simulation,
                args=(self.config,),
                daemon=True,
            )
            _SimulatorState.thread.start()
            self._send_json({"status": "ok"})
            return

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
            file_name = params.get("file_name", [""])[0]

            if file_path and series_name:
                input_folder = _resolve_runtime_path(self.config, "input_folder")
                source = _find_photo_path(file_path, input_folder, file_name)
                if source is not None:
                    selected_dir = Path(self.config["paths"]["output_selected"])
                    dest = rescue_photo(source, selected_dir, series_name)
                    _sync_rescued_to_network([dest], self.config)
                    SeriesBrowserHandler._series_cache = None

            self._send_redirect(f"/series/{series_name}")

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
