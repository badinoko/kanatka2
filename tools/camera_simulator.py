from __future__ import annotations

import argparse
import random
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from config_utils import ensure_runtime_directories, load_config
from image_utils import list_image_files
from logger_setup import build_logger


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def _is_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def load_series_from_folders(source: Path, rng: random.Random, shuffle_series: bool = True) -> list[list[Path]]:
    """Load pre-organized series from subfolders.

    Each subfolder in *source* is one series.  Files inside each folder
    are sorted by name (preserving frame order within a series).
    The order of series themselves is shuffled to simulate real randomness.
    """
    series: list[list[Path]] = []
    for folder in sorted(source.iterdir()):
        if not folder.is_dir():
            continue
        if folder.name.startswith((".", "_")):
            continue
        files = sorted([f for f in folder.iterdir() if _is_image(f)])
        if files:
            series.append(files)
    if shuffle_series:
        rng.shuffle(series)
    return series


def split_flat_files(files: list[Path], size: int, rng: random.Random) -> list[list[Path]]:
    """Split a flat list of files into series of fixed size."""
    rng.shuffle(files)
    series: list[list[Path]] = []
    for i in range(0, len(files), size):
        chunk = files[i:i + size]
        if chunk:
            series.append(chunk)
    return series


def main() -> int:
    parser = argparse.ArgumentParser(description="Симулятор камеры")
    parser.add_argument("--config", default=None)
    parser.add_argument("--source", default=None,
                        help="Папка с фото. Если содержит подпапки — каждая = серия.")
    parser.add_argument("--target", default=None)
    parser.add_argument("--series-size", type=int, default=8,
                        help="Размер серии для плоской папки (по умолчанию 8)")
    parser.add_argument("--frame-delay", type=float, default=0.2,
                        help="Задержка между кадрами в серии (сек)")
    parser.add_argument("--series-delay-min", type=float, default=12.0)
    parser.add_argument("--series-delay-max", type=float, default=20.0)
    parser.add_argument("--no-shuffle", action="store_true",
                        help="Не перемешивать порядок серий")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    config = load_config(args.config)
    ensure_runtime_directories(config)
    logger = build_logger(config["paths"]["log_dir"])

    source_folder = Path(args.source or config["paths"]["test_photos_folder"])
    target_folder = Path(args.target or config["paths"]["input_folder"])
    target_folder.mkdir(parents=True, exist_ok=True)

    rng = random.Random(args.seed)

    # Detect mode: subfolders (organized series) or flat files (random grouping)
    subdirs = [d for d in source_folder.iterdir() if d.is_dir() and not d.name.startswith((".", "_"))]

    if subdirs:
        series_list = load_series_from_folders(source_folder, rng, shuffle_series=not args.no_shuffle)
        logger.info("Режим подпапок: %d серий найдено", len(series_list))
    else:
        files = [f for f in source_folder.iterdir() if _is_image(f)]
        if not files:
            logger.warning("Нет изображений в %s", source_folder)
            return 1
        series_list = split_flat_files(files, args.series_size, rng)
        logger.info("Плоский режим: %d файлов → %d серий по %d",
                     len(files), len(series_list), args.series_size)

    total_files = sum(len(s) for s in series_list)
    logger.info("Всего: %d серий, %d файлов", len(series_list), total_files)

    for series_index, series in enumerate(series_list, start=1):
        for frame_index, photo_path in enumerate(series, start=1):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            target_name = f"SER{series_index:03d}_IMG{frame_index:03d}_{timestamp}{photo_path.suffix.lower()}"
            target_path = target_folder / target_name
            shutil.copy(photo_path, target_path)
            logger.info(
                "Серия %d/%d, кадр %d/%d -> %s",
                series_index,
                len(series_list),
                frame_index,
                len(series),
                target_path.name,
            )
            time.sleep(args.frame_delay)

        if series_index != len(series_list):
            delay = rng.uniform(args.series_delay_min, args.series_delay_max)
            logger.info("Пауза между сериями %.1f сек", delay)
            time.sleep(delay)

    logger.info("Симуляция завершена: %d серий, %d файлов отправлено", len(series_list), total_files)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
