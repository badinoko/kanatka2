from __future__ import annotations

import argparse
from pathlib import Path

from config_utils import ensure_runtime_directories, load_config
from gui import launch_gui
from logger_setup import build_logger
from sheet_composer import compose_pending_sheets
from watcher import process_folder, watch_incoming_folder


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PhotoSelector MVP")
    parser.add_argument("--config", default=None, help="Путь до config.json")

    subparsers = parser.add_subparsers(dest="command")

    process_parser = subparsers.add_parser("process", help="Обработать папку с фотографиями")
    process_parser.add_argument("--source", default=None, help="Папка с исходными JPG")
    process_parser.add_argument("--save-annotations", action="store_true", help="Сохранять annotated JPG")

    subparsers.add_parser("watch", help="Следить за папкой incoming")
    subparsers.add_parser("sheet", help="Собрать листы из selected")
    subparsers.add_parser("gui", help="Запустить графический интерфейс")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        launch_gui(args.config)
        return 0

    config = load_config(args.config)
    ensure_runtime_directories(config)
    logger = build_logger(config["paths"]["log_dir"])

    if args.command == "gui":
        launch_gui(args.config)
        return 0

    if args.command == "watch":
        watch_incoming_folder(config, logger)
        return 0

    if args.command == "sheet":
        generated = compose_pending_sheets(config, logger)
        print(f"Собрано листов: {len(generated)}")
        return 0

    if args.command == "process":
        source_folder = Path(args.source or config["paths"]["test_photos_folder"])
        summary = process_folder(
            source_folder,
            config,
            logger,
            remove_source_files=False,
            save_annotations=args.save_annotations,
        )
        print(
            "Готово:"
            f" серий={summary['series_total']},"
            f" выбрано={summary['selected_total']},"
            f" пустых={summary['discarded_total']},"
            f" листов={summary['sheets_total']}"
        )
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
