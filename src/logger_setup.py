from __future__ import annotations

import logging
from pathlib import Path


def build_logger(log_dir: str | Path, log_to_file: bool = True) -> logging.Logger:
    log_directory = Path(log_dir)
    log_directory.mkdir(parents=True, exist_ok=True)
    log_path = log_directory / "photo_selector.log"

    logger = logging.getLogger("photo_selector")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if log_to_file:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    return logger
