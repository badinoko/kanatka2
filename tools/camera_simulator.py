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
from image_utils import list_jpeg_files
from logger_setup import build_logger


def split_into_series(files: list[Path], min_size: int, max_size: int, rng: random.Random) -> list[list[Path]]:
    pool = list(files)
    series: list[list[Path]] = []
    while pool:
        size = rng.randint(min_size, max_size)
        chunk = pool[:size]
        pool = pool[size:]
        if chunk:
            series.append(chunk)
    return series


def main() -> int:
    parser = argparse.ArgumentParser(description="Симулятор камеры")
    parser.add_argument("--config", default=None)
    parser.add_argument("--source", default=None)
    parser.add_argument("--target", default=None)
    parser.add_argument("--min-series", type=int, default=5)
    parser.add_argument("--max-series", type=int, default=7)
    parser.add_argument("--frame-delay", type=float, default=0.2)
    parser.add_argument("--series-delay-min", type=float, default=12.0)
    parser.add_argument("--series-delay-max", type=float, default=20.0)
    parser.add_argument("--shuffle", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    config = load_config(args.config)
    ensure_runtime_directories(config)
    logger = build_logger(config["paths"]["log_dir"])

    source_folder = Path(args.source or config["paths"]["test_photos_folder"])
    target_folder = Path(args.target or config["paths"]["input_folder"])
    target_folder.mkdir(parents=True, exist_ok=True)

    files = list_jpeg_files(source_folder)
    rng = random.Random(args.seed)
    if args.shuffle:
        rng.shuffle(files)

    series_list = split_into_series(files, args.min_series, args.max_series, rng)

    for series_index, series in enumerate(series_list, start=1):
        for frame_index, photo_path in enumerate(series, start=1):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            target_name = f"SER{series_index:03d}_IMG{frame_index:03d}_{timestamp}{photo_path.suffix.lower()}"
            target_path = target_folder / target_name
            shutil.copy2(photo_path, target_path)
            logger.info(
                "Серия %s, кадр %s/%s -> %s",
                series_index,
                frame_index,
                len(series),
                target_path.name,
            )
            time.sleep(args.frame_delay)

        if series_index != len(series_list):
            delay = rng.uniform(args.series_delay_min, args.series_delay_max)
            logger.info("Пауза между сериями %.1f сек", delay)
            time.sleep(delay)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
