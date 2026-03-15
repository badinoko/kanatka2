"""Receiver HTTP server — lightweight sheet viewer for the print shop.

Serves a simple web UI with auto-refreshing grid of sheet thumbnails.
No ML dependencies, minimal footprint.
"""
from __future__ import annotations

import io
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore[assignment,misc]

from receiver_watcher import SheetQueue

_HTML_PAGE = """\
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Канатка — Приёмник листов</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       background: #f0f2f5; color: #333; }
.navbar { background: #2c3e50; color: #fff; padding: 12px 24px;
          display: flex; align-items: center; gap: 12px;
          box-shadow: 0 2px 4px rgba(0,0,0,.15); }
.navbar h1 { font-size: 18px; font-weight: 600; }
.status-dot { width: 10px; height: 10px; border-radius: 50%;
              background: #2ecc71; display: inline-block; }
.status-label { font-size: 13px; opacity: .85; }
.container { max-width: 1400px; margin: 24px auto; padding: 0 16px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
        gap: 16px; }
.card { background: #fff; border-radius: 8px; overflow: hidden;
        box-shadow: 0 1px 3px rgba(0,0,0,.1); cursor: pointer;
        transition: transform .15s, box-shadow .15s; }
.card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,.15); }
.card img { width: 100%; height: 240px; object-fit: cover; display: block; }
.card-footer { padding: 8px 12px; font-size: 13px; color: #555;
               white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.empty-msg { text-align: center; padding: 80px 20px; color: #999; font-size: 16px; }
.modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.85);
                 z-index: 1000; justify-content: center; align-items: center; }
.modal-overlay.active { display: flex; }
.modal-overlay img { max-width: 95vw; max-height: 95vh; object-fit: contain; }
</style>
</head>
<body>
<div class="navbar">
  <span class="status-dot" id="statusDot"></span>
  <h1>Канатка — Приёмник листов</h1>
  <span class="status-label" id="statusLabel">Обновление...</span>
</div>
<div class="container">
  <div class="grid" id="grid"></div>
  <div class="empty-msg" id="emptyMsg">Листы не найдены. Ожидание...</div>
</div>
<div class="modal-overlay" id="modal">
  <img id="modalImg" src="" alt="">
</div>
<script>
(function() {
  var grid = document.getElementById('grid');
  var emptyMsg = document.getElementById('emptyMsg');
  var modal = document.getElementById('modal');
  var modalImg = document.getElementById('modalImg');
  var statusDot = document.getElementById('statusDot');
  var statusLabel = document.getElementById('statusLabel');

  modal.addEventListener('click', function() {
    modal.classList.remove('active');
    modalImg.src = '';
  });

  function showFull(filename) {
    modalImg.src = '/full/' + encodeURIComponent(filename);
    modal.classList.add('active');
  }

  function buildCard(sheet) {
    var card = document.createElement('div');
    card.className = 'card';
    var img = document.createElement('img');
    img.src = '/thumb/' + encodeURIComponent(sheet.filename);
    img.alt = sheet.filename;
    img.loading = 'lazy';
    card.appendChild(img);
    var footer = document.createElement('div');
    footer.className = 'card-footer';
    footer.textContent = sheet.filename;
    card.appendChild(footer);
    card.addEventListener('click', function() { showFull(sheet.filename); });
    return card;
  }

  function refresh() {
    fetch('/api/sheets')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        statusDot.style.background = '#2ecc71';
        statusLabel.textContent = 'Листов: ' + data.sheets.length;
        if (data.sheets.length === 0) {
          grid.style.display = 'none';
          emptyMsg.style.display = 'block';
          return;
        }
        emptyMsg.style.display = 'none';
        grid.style.display = '';
        // rebuild grid
        while (grid.firstChild) { grid.removeChild(grid.firstChild); }
        data.sheets.forEach(function(s) { grid.appendChild(buildCard(s)); });
      })
      .catch(function() {
        statusDot.style.background = '#e74c3c';
        statusLabel.textContent = 'Нет связи';
      });
  }

  refresh();
  setInterval(refresh, 3000);
})();
</script>
</body>
</html>
"""


def _make_thumbnail(filepath: Path, size: int = 400) -> bytes:
    """Create a JPEG thumbnail of the given image."""
    if Image is None:
        # Fallback: return original file bytes
        return filepath.read_bytes()
    img = Image.open(filepath)
    img.thumbnail((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def _make_handler(queue: SheetQueue):
    """Create a request handler class bound to the given queue."""

    class ReceiverHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            # Suppress default logging
            pass

        def do_GET(self):
            path = unquote(self.path)

            if path == "/" or path == "":
                self._serve_html()
            elif path == "/api/sheets":
                self._serve_api_sheets()
            elif path.startswith("/thumb/"):
                self._serve_image(path[7:], thumbnail=True)
            elif path.startswith("/full/"):
                self._serve_image(path[6:], thumbnail=False)
            else:
                self._send_error(404, "Not Found")

        def _serve_html(self):
            body = _HTML_PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _serve_api_sheets(self):
            items = queue.get_latest()
            sheets = []
            for p in items:
                entry = {"filename": p.name}
                try:
                    entry["size"] = p.stat().st_size
                except OSError:
                    entry["size"] = 0
                sheets.append(entry)
            body = json.dumps({"sheets": sheets}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _serve_image(self, filename: str, thumbnail: bool):
            # Find the file in the queue
            items = queue.get_latest()
            target = None
            for p in items:
                if p.name == filename:
                    target = p
                    break
            if target is None or not target.exists():
                self._send_error(404, "Image not found")
                return
            try:
                if thumbnail:
                    data = _make_thumbnail(target)
                else:
                    data = target.read_bytes()
            except Exception:
                self._send_error(500, "Error reading image")
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_error(self, code: int, message: str):
            body = message.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return ReceiverHandler


def create_receiver_server(queue: SheetQueue, port: int = 8788) -> ThreadingHTTPServer:
    """Create and return a ThreadingHTTPServer (not yet started)."""
    handler = _make_handler(queue)
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    return server
