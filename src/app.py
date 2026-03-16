"""Standalone pywebview application for PhotoSelector.

Launches the HTTP server and opens a native window (WebView2 on Windows)
instead of a browser tab. This is the primary entry point for end users.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/ is importable when running as script or from PyInstaller bundle
_src_dir = Path(__file__).resolve().parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from config_utils import ensure_runtime_directories, load_config
from logger_setup import build_logger
from series_browser import start_server

PORT = 8787
WINDOW_TITLE = "PhotoSelector — Канатка"
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 800


def launch_app(config_path: str | None = None) -> None:
    """Start HTTP server and open pywebview window."""
    import webview

    config = load_config(config_path)
    ensure_runtime_directories(config)
    logger = build_logger(config["paths"]["log_dir"], log_to_file=config.get("logging", {}).get("log_to_file", True))

    server_thread = start_server(config, port=PORT)
    logger.info("HTTP-сервер запущен на http://127.0.0.1:%s", PORT)

    window = webview.create_window(
        WINDOW_TITLE,
        url=f"http://127.0.0.1:{PORT}",
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT,
        resizable=True,
        min_size=(800, 600),
        confirm_close=True,
    )
    webview.start()
    logger.info("Приложение завершено")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="PhotoSelector — Канатка")
    parser.add_argument("--config", default=None, help="Путь до config.json")
    args = parser.parse_args()
    launch_app(args.config)
