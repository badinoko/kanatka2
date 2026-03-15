from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from analyzer import analyze_photo
from config_utils import ensure_runtime_directories, load_config
from face_utils import MediaPipeFaceAnalyzer
from image_utils import list_jpeg_files, save_image
from logger_setup import build_logger


def main() -> int:
    parser = argparse.ArgumentParser(description="POC для MediaPipe на тестовых фото")
    parser.add_argument("--config", default=None)
    parser.add_argument("--source", default=None)
    parser.add_argument("--output", default=str(ROOT / "poc_results"))
    args = parser.parse_args()

    config = load_config(args.config)
    ensure_runtime_directories(config)
    logger = build_logger(config["paths"]["log_dir"])

    source_folder = Path(args.source or config["paths"]["test_photos_folder"])
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    analyzer = MediaPipeFaceAnalyzer(config["thresholds"]["min_face_confidence"])
    report_lines = []

    try:
        for photo_path in list_jpeg_files(source_folder):
            metrics, annotated = analyze_photo(photo_path, analyzer, config)
            save_image(output_dir / f"{photo_path.stem}_annotated.jpg", annotated)
            report_lines.append(
                f"{photo_path.name} | faces={metrics['face_count']} | score={metrics['score']:.2f} | "
                f"sharp={metrics['overall_sharpness']:.1f} | time={metrics['timings']['total_seconds']:.2f}s"
            )
            logger.info("POC: %s -> faces=%s score=%.2f", photo_path.name, metrics["face_count"], metrics["score"])
    finally:
        analyzer.close()

    (output_dir / "report.txt").write_text("\n".join(report_lines), encoding="utf-8")
    print(f"Готово. Отчёт: {output_dir / 'report.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
