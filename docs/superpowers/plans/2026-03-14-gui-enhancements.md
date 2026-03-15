# GUI Enhancements: Web Browser + Network Sync + ZIP Export

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add web-based series browser (rescue missed photos), network auto-copy of sheets, ZIP export, and GUI buttons to wire it all together.

**Architecture:** Web viewer runs as a local HTTP server (stdlib `http.server`, zero dependencies) with embedded HTML/CSS/JS. Serves photos directly from workdir, reads `ser*_report.json` for metadata. Network sync copies sheets to a configurable UNC/shared path. ZIP packs selected+sheets for manual transfer.

**Tech Stack:** Python stdlib (`http.server`, `json`, `zipfile`, `shutil`), embedded HTML+CSS+JS (no frontend build), tkinter (existing GUI).

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/series_browser.py` | Create | Web server + HTML template for series browsing |
| `src/export_utils.py` | Create | ZIP export + network sync utilities |
| `src/gui.py` | Modify | Add buttons: "Просмотр серий", "Упаковать ZIP", network sync toggle |
| `src/config.json` | Modify | Add `network` section with `output_path` and `auto_sync` |
| `tests/test_export_utils.py` | Create | Tests for ZIP and network copy |
| `tests/test_series_browser.py` | Create | Tests for series data loading |

---

## Chunk 1: Series Browser

### Task 1: Series data loader

**Files:**
- Create: `src/series_browser.py`
- Test: `tests/test_series_browser.py`

- [ ] **Step 1:** Write test for `load_all_series()` that reads report JSONs
- [ ] **Step 2:** Implement `load_all_series(log_dir)` — returns list of series dicts
- [ ] **Step 3:** Write test for `rescue_photo()` — copies photo to selected
- [ ] **Step 4:** Implement `rescue_photo(source_path, selected_dir, series_name)`
- [ ] **Step 5:** Run tests, commit

### Task 2: HTTP server + HTML UI

**Files:**
- Modify: `src/series_browser.py`

- [ ] **Step 1:** Implement `SeriesBrowserHandler(BaseHTTPRequestHandler)`:
  - `GET /` — series list page (HTML)
  - `GET /series/<name>` — series detail with all photos
  - `GET /photo/<path>` — serve JPEG from disk
  - `POST /rescue` — copy photo to selected, redirect back
- [ ] **Step 2:** Implement `start_browser_server(config, port=8787)` — starts server + opens browser
- [ ] **Step 3:** Build embedded HTML template with:
  - Series list: thumbnails, status badges, score
  - Series detail: all photos grid, "Спасти" button per photo
  - Responsive layout, Russian labels
- [ ] **Step 4:** Manual test in browser, commit

### Task 3: GUI integration — browser button

**Files:**
- Modify: `src/gui.py`

- [ ] **Step 1:** Add "Просмотр серий" button to button_frame
- [ ] **Step 2:** On click: start browser server in background thread, open browser
- [ ] **Step 3:** Commit

---

## Chunk 2: Export + Network Sync

### Task 4: ZIP export

**Files:**
- Create: `src/export_utils.py`
- Test: `tests/test_export_utils.py`

- [ ] **Step 1:** Write test for `create_results_zip()`
- [ ] **Step 2:** Implement: packs selected/ + sheets/ into timestamped ZIP on Desktop
- [ ] **Step 3:** Run tests, commit

### Task 5: Network sync

**Files:**
- Modify: `src/export_utils.py`
- Modify: `src/config.json`

- [ ] **Step 1:** Add `network` section to config: `{"output_path": "", "auto_sync_sheets": false}`
- [ ] **Step 2:** Implement `sync_sheets_to_network(sheets_dir, network_path)` — copies new sheets
- [ ] **Step 3:** Wire auto-sync into `sheet_composer.compose_pending_sheets()` if enabled
- [ ] **Step 4:** Commit

### Task 6: GUI integration — export buttons

**Files:**
- Modify: `src/gui.py`

- [ ] **Step 1:** Add "Упаковать ZIP" button
- [ ] **Step 2:** Add "Сетевая папка" entry + toggle in settings area
- [ ] **Step 3:** Commit

---

## Chunk 3: Documentation

### Task 7: Update project docs

- [ ] **Step 1:** Update `docs/project/overview.md` dashboard
- [ ] **Step 2:** Append to `docs/project/progress.md`
- [ ] **Step 3:** Update `docs/project/startup.md`
- [ ] **Step 4:** Commit
