"""Folder watcher for the receiver app.

Monitors a folder (typically SMB network share) for new sheet images
and maintains a queue of recent items for the UI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

JPEG_EXTENSIONS = {".jpg", ".jpeg"}


@dataclass
class SheetQueue:
    """Thread-safe queue of recently received sheet image paths."""

    max_items: int = 50
    _items: list[Path] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock)

    def add(self, path: Path) -> None:
        with self._lock:
            if any(p.name == path.name for p in self._items):
                return
            self._items.append(path)
            if len(self._items) > self.max_items:
                self._items = self._items[-self.max_items:]

    def get_latest(self, count: int | None = None) -> list[Path]:
        with self._lock:
            items = list(reversed(self._items))
            if count is not None:
                return items[:count]
            return items

    def scan_folder(self, folder: Path) -> None:
        if not folder.exists():
            return
        files = sorted(
            [f for f in folder.iterdir() if f.suffix.lower() in JPEG_EXTENSIONS],
            key=lambda p: p.stat().st_mtime,
        )
        for f in files:
            self.add(f)


class SheetFolderHandler(FileSystemEventHandler):
    def __init__(self, queue: SheetQueue) -> None:
        self.queue = queue

    def on_created(self, event) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() in JPEG_EXTENSIONS:
            self.queue.add(path)

    def on_moved(self, event) -> None:
        if event.is_directory:
            return
        path = Path(event.dest_path)
        if path.suffix.lower() in JPEG_EXTENSIONS:
            self.queue.add(path)


def start_watcher(folder: Path, queue: SheetQueue) -> Observer:
    folder.mkdir(parents=True, exist_ok=True)
    queue.scan_folder(folder)
    observer = Observer()
    observer.schedule(SheetFolderHandler(queue), str(folder), recursive=False)
    observer.start()
    return observer
