"""Receiver app — lightweight sheet viewer for the print shop.

Watches a folder for new print sheets and displays them in a native window.
No ML dependencies, minimal footprint for weak hardware (i3/8GB).
"""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

_receiver_dir = Path(__file__).resolve().parent
if str(_receiver_dir) not in sys.path:
    sys.path.insert(0, str(_receiver_dir))

from receiver_server import create_receiver_server
from receiver_watcher import SheetQueue, start_watcher

CONFIG_FILE = _receiver_dir / "receiver_config.json"
DEFAULT_CONFIG = {
    "watched_folder": "",
    "port": 8788,
    "refresh_interval_seconds": 3,
    "thumbnails_per_page": 20,
    "window_title": "Канатка — Приёмник листов",
}


def _load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return {**DEFAULT_CONFIG, **data}
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULT_CONFIG)


def _save_config(config: dict) -> None:
    CONFIG_FILE.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _pick_folder_dialog() -> str | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        folder = filedialog.askdirectory(title="Выберите папку с листами")
        root.destroy()
        return folder if folder else None
    except Exception:
        return None


def launch_receiver() -> None:
    import webview

    config = _load_config()

    if not config["watched_folder"]:
        folder = _pick_folder_dialog()
        if not folder:
            print("Папка не выбрана. Выход.")
            sys.exit(0)
        config["watched_folder"] = folder
        _save_config(config)

    watched = Path(config["watched_folder"])
    if not watched.exists():
        try:
            watched.mkdir(parents=True, exist_ok=True)
        except OSError:
            print(f"Не удалось создать папку: {watched}")
            sys.exit(1)

    queue = SheetQueue(max_items=config["thumbnails_per_page"])
    observer = start_watcher(watched, queue)

    port = config["port"]
    server = create_receiver_server(queue, port=port)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    window = webview.create_window(
        config["window_title"],
        url=f"http://127.0.0.1:{port}",
        width=1280,
        height=800,
        resizable=True,
        min_size=(800, 600),
    )
    webview.start()

    observer.stop()
    observer.join()
    server.shutdown()


if __name__ == "__main__":
    launch_receiver()
