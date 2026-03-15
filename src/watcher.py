from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from face_utils import MediaPipeFaceAnalyzer
from image_utils import list_jpeg_files
from print_utils import print_sheet
from selector import process_series
from sheet_composer import compose_pending_sheets


def group_files_by_time(file_paths: list[Path], max_gap_seconds: float) -> list[list[Path]]:
    if not file_paths:
        return []

    sorted_files = sorted(file_paths, key=lambda path: (path.stat().st_mtime, path.name.lower()))
    groups = [[sorted_files[0]]]
    previous_path = sorted_files[0]

    for current_path in sorted_files[1:]:
        gap = current_path.stat().st_mtime - previous_path.stat().st_mtime
        if gap <= max_gap_seconds:
            groups[-1].append(current_path)
        else:
            groups.append([current_path])
        previous_path = current_path

    return groups


def _autoprint_sheets(sheets: list, config: dict, logger) -> None:
    """Print sheets if autoprint is enabled and test_mode is off."""
    print_config = config.get("print", {})
    if not print_config.get("autoprint", False):
        return
    if print_config.get("test_mode", True):
        logger.info("Автопечать пропущена: включён тестовый режим")
        return
    printer_name = print_config.get("printer_name", "")
    for sheet_path in sheets:
        ok = print_sheet(Path(sheet_path), printer_name)
        if ok:
            logger.info("Лист отправлен на печать: %s", sheet_path)
        else:
            logger.warning("Ошибка печати листа: %s", sheet_path)


def process_folder(
    source_folder: str | Path,
    config: dict,
    logger,
    remove_source_files: bool = False,
    save_annotations: bool = False,
) -> dict:
    source = Path(source_folder)
    files = list_jpeg_files(source)
    groups = group_files_by_time(files, config["series_detection"]["max_gap_seconds"])

    if not groups:
        return {"series_total": 0, "selected_total": 0, "discarded_total": 0, "sheets_total": 0}

    analyzer = MediaPipeFaceAnalyzer(config["thresholds"]["min_face_confidence"])
    results = []
    try:
        for index, group in enumerate(groups, start=1):
            results.append(
                process_series(
                    group,
                    index,
                    analyzer,
                    config,
                    logger,
                    remove_source_files=remove_source_files,
                    save_annotations=save_annotations,
                )
            )
    finally:
        analyzer.close()

    generated_sheets = compose_pending_sheets(config, logger, allow_partial=False)

    _autoprint_sheets(generated_sheets, config, logger)

    return {
        "series_total": len(groups),
        "selected_total": sum(result["status"] == "selected" for result in results),
        "ambiguous_total": sum(result["status"] == "ambiguous_manual_review" for result in results),
        "discarded_total": sum(result["status"] == "discarded_empty" for result in results),
        "sheets_total": len(generated_sheets),
        "results": results,
    }


@dataclass
class PendingQueue:
    files: list[Path] = field(default_factory=list)
    last_event_time: float = 0.0
    lock: Lock = field(default_factory=Lock)

    def add(self, file_path: Path) -> None:
        with self.lock:
            if file_path not in self.files:
                self.files.append(file_path)
            self.last_event_time = time.time()

    def flush_ready(self, cooldown_seconds: float) -> list[Path]:
        with self.lock:
            if not self.files:
                return []
            if time.time() - self.last_event_time < cooldown_seconds:
                return []
            ready = list(self.files)
            self.files.clear()
            return ready


class IncomingFolderHandler(FileSystemEventHandler):
    def __init__(self, pending_queue: PendingQueue) -> None:
        self.pending_queue = pending_queue

    def on_created(self, event) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
            self.pending_queue.add(path)

    def on_moved(self, event) -> None:
        if event.is_directory:
            return
        path = Path(event.dest_path)
        if path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
            self.pending_queue.add(path)


def watch_incoming_folder(config: dict, logger) -> None:
    incoming_dir = Path(config["paths"]["input_folder"])
    incoming_dir.mkdir(parents=True, exist_ok=True)

    analyzer = MediaPipeFaceAnalyzer(config["thresholds"]["min_face_confidence"])
    pending_queue = PendingQueue()
    observer = Observer()
    observer.schedule(IncomingFolderHandler(pending_queue), str(incoming_dir), recursive=False)
    observer.start()

    logger.info("Запущен мониторинг папки %s", incoming_dir)
    series_index = 1

    try:
        while True:
            ready_files = pending_queue.flush_ready(config["series_detection"]["cooldown_seconds"])
            if ready_files:
                grouped = group_files_by_time(ready_files, config["series_detection"]["max_gap_seconds"])
                for group in grouped:
                    process_series(
                        group,
                        series_index,
                        analyzer,
                        config,
                        logger,
                        remove_source_files=True,
                        save_annotations=True,
                    )
                    sheets = compose_pending_sheets(config, logger)
                    _autoprint_sheets(sheets, config, logger)
                    series_index += 1
            time.sleep(0.5)
    finally:
        observer.stop()
        observer.join()
        analyzer.close()
