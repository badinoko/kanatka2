# KAN-030 + KAN-031 + KAN-019 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace browser-based UI with standalone pywebview app, create receiver app for print shop, package both as EXEs with PyInstaller.

**Architecture:** Main app wraps existing HTTP server (series_browser.py) in a pywebview native window. Receiver is an independent lightweight app that watches a folder for new sheet images. Both are packaged as standalone Windows EXEs via PyInstaller.

**Tech Stack:** Python 3.11+, pywebview (WebView2/Edge), PyInstaller, watchdog, Pillow, stdlib http.server

---

## File Map

### New Files
| File | Purpose |
|------|---------|
| `src/app.py` | pywebview launcher for main app (KAN-030) |
| `receiver/receiver_app.py` | Receiver pywebview entry point |
| `receiver/receiver_server.py` | Lightweight HTTP server for receiver UI |
| `receiver/receiver_watcher.py` | Watchdog folder watcher for receiver |
| `receiver/receiver_config.json` | Default receiver config |
| `build/kanatka.spec` | PyInstaller spec for main app |
| `build/receiver.spec` | PyInstaller spec for receiver |
| `build/build.py` | Build script for both EXEs |
| `run_app.bat` | Batch launcher for pywebview app |
| `run_receiver.bat` | Batch launcher for receiver |
| `tests/test_app.py` | Tests for app.py |
| `tests/test_receiver_server.py` | Tests for receiver server |
| `tests/test_receiver_watcher.py` | Tests for receiver watcher |

### Modified Files
| File | Change |
|------|--------|
| `src/series_browser.py` | Extract `start_server()` from `start_browser()` |
| `src/main.py` | Add `app` command, change default |
| `requirements.txt` | Add `pywebview` |

---

## Chunk 1: KAN-030 — Embedded Window (pywebview)

### Task 1: Install pywebview

- [ ] **Step 1: Install pywebview into venv**

Run: `cd C:/Users/user/Projects/kanatka2 && .venv/Scripts/pip.exe install pywebview`

- [ ] **Step 2: Verify import**

Run: `.venv/Scripts/python.exe -c "import webview; print(webview.__version__)"`

- [ ] **Step 3: Add to requirements.txt** (after `pillow` alphabetically)

- [ ] **Step 4: Commit**

### Task 2: Extract start_server from series_browser.py

- [ ] **Step 1: Write failing test** (`tests/test_app.py` — test that `start_server` exists and does not open browser)

- [ ] **Step 2: Run test — verify fails**

- [ ] **Step 3: Refactor series_browser.py** — split `start_browser()` into `start_server()` (no browser) + `start_browser()` (calls `start_server` + opens browser)

- [ ] **Step 4: Run tests — verify pass**

- [ ] **Step 5: Run all existing 24 tests — no regressions**

- [ ] **Step 6: Commit**

### Task 3: Create app.py

- [ ] **Step 1: Write test** — `launch_app` is callable

- [ ] **Step 2: Create `src/app.py`** — loads config, starts server, opens pywebview window

- [ ] **Step 3: Run tests — pass**

- [ ] **Step 4: Commit**

### Task 4: Update main.py and create run_app.bat

- [ ] **Step 1: Update main.py** — default command uses `launch_app`, add `app` subcommand

- [ ] **Step 2: Create `run_app.bat`**

- [ ] **Step 3: Run all tests**

- [ ] **Step 4: Manual smoke test** — pywebview window opens with series browser

- [ ] **Step 5: Commit**

---

## Chunk 2: KAN-031 — Receiver App

### Task 5: Create receiver directory and config

- [ ] **Step 1: Create `receiver/` directory**

- [ ] **Step 2: Create `receiver/receiver_config.json`** — watched_folder, port 8788, refresh interval

- [ ] **Step 3: Commit**

### Task 6: Receiver watcher

- [ ] **Step 1: Write test** (`tests/test_receiver_watcher.py` — SheetQueue add/list, max limit, no dupes, scan folder)

- [ ] **Step 2: Run test — fails**

- [ ] **Step 3: Implement `receiver/receiver_watcher.py`** — SheetQueue, SheetFolderHandler, start_watcher

- [ ] **Step 4: Run tests — pass**

- [ ] **Step 5: Commit**

### Task 7: Receiver HTTP server

- [ ] **Step 1: Write test** (`tests/test_receiver_server.py` — root returns HTML, /api/sheets returns JSON, 404 for unknown)

- [ ] **Step 2: Run test — fails**

- [ ] **Step 3: Implement `receiver/receiver_server.py`** — ReceiverHandler, create_receiver_server, HTML UI with auto-refresh

- [ ] **Step 4: Run tests — pass**

- [ ] **Step 5: Commit**

### Task 8: Receiver app entry point

- [ ] **Step 1: Create `receiver/receiver_app.py`** — load config, pick folder dialog if needed, start watcher + server + pywebview

- [ ] **Step 2: Create `run_receiver.bat`**

- [ ] **Step 3: Commit**

---

## Chunk 3: KAN-019 — PyInstaller Packaging

### Task 9: Create build infrastructure

- [ ] **Step 1: Install PyInstaller** into venv

- [ ] **Step 2: Create `build/` directory**

- [ ] **Step 3: Create `build/kanatka.spec`** — main app with models/ data, hidden imports for mediapipe/cv2/webview

- [ ] **Step 4: Create `build/receiver.spec`** — receiver app, excludes numpy/cv2/mediapipe

- [ ] **Step 5: Create `build/build.py`** — CLI script to build --main, --receiver, or --all

- [ ] **Step 6: Commit**

### Task 10: Test builds

- [ ] **Step 1: Build main app** — verify dist/PhotoSelector/ created

- [ ] **Step 2: Build receiver** — verify dist/KanatkaReceiver/ created

- [ ] **Step 3: Smoke test both EXEs**

- [ ] **Step 4: Fix any PyInstaller issues** (missing imports, data files)

- [ ] **Step 5: Commit**

### Task 11: Final verification

- [ ] **Step 1: Run full test suite** — all ~33 tests pass

- [ ] **Step 2: Update .gitignore** — dist/, build/work_*/

- [ ] **Step 3: Final commit**
