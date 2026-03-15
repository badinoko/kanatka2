# KAN-030 + KAN-031 + KAN-019 Design Spec

## KAN-030: Embedded Window (pywebview)

Replace tkinter launcher + browser tab with pywebview — native window with embedded WebView2 (Edge on Windows). User sees one standalone application.

**Approach:**
- New `src/app.py` — main entry point replacing `gui.py`
- HTTP server (`series_browser.py`) starts on 127.0.0.1:8787 as before
- pywebview opens a window pointing at `http://127.0.0.1:8787`
- Window: title "PhotoSelector — Канатка", 1280x800, resizable
- `_kill_old_server()` called at startup
- On window close — application exits
- `gui.py` remains as fallback (not deleted per project rules)
- `main.py` updated: default command launches `app.py` instead of `gui.py`
- `run_app.bat` — new batch file for pywebview launch

## KAN-031: Receiver App

Lightweight program for print shop computer (i3/8GB). Watches a folder for new sheet images, displays them to operator.

**Approach:**
- New directory `receiver/` with:
  - `receiver_app.py` — pywebview entry point
  - `receiver_server.py` — lightweight HTTP server (stdlib only)
  - `receiver_watcher.py` — watchdog folder watcher
  - `receiver_config.json` — minimal config (watched folder path)
- Single page UI: grid of latest sheets, large previews, auto-refresh
- First launch: dialog to select watched folder, saves to config
- No ML dependencies (no MediaPipe, no OpenCV) — only Pillow for thumbnails
- Uses watchdog for real-time folder monitoring
- `run_receiver.bat` — batch file for receiver

## KAN-019: PyInstaller Packaging

Two standalone EXE files.

**Approach:**
- `build/kanatka.spec` — main program (app.py + src/ + models/)
- `build/receiver.spec` — receiver (receiver/ + Pillow + watchdog)
- `build/build.py` — build script for both EXEs
- Main EXE: ~200-400 MB (MediaPipe + OpenCV + pywebview)
- Receiver EXE: ~30-50 MB (Pillow + watchdog + pywebview)
- Both are `--windowed` (no console window)
- Icon: placeholder .ico file

## New Dependencies
- `pywebview` — both apps
- `pyinstaller` — build only (dev)
