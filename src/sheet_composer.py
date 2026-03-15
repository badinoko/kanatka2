from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

from badge_utils import add_score_badge
from metadata_utils import build_photo_metadata_path, photo_metadata_enabled


def compose_sheet(image_paths: list[Path], output_path: str | Path, sheet_config: dict) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    columns = sheet_config["grid_columns"]
    rows = sheet_config["grid_rows"]
    sheet_width = sheet_config["sheet_width_px"]
    sheet_height = sheet_config["sheet_height_px"]
    padding = sheet_config["cell_padding_px"]

    cell_width = (sheet_width - padding * (columns + 1)) // columns
    cell_height = (sheet_height - padding * (rows + 1)) // rows

    canvas = Image.new("RGB", (sheet_width, sheet_height), color=(250, 250, 250))
    show_score_badge = bool(sheet_config.get("show_score_badge", True))

    for index, image_path in enumerate(image_paths):
        row = index // columns
        column = index % columns
        offset_x = padding + column * (cell_width + padding)
        offset_y = padding + row * (cell_height + padding)

        with Image.open(image_path) as source_image:
            prepared = ImageOps.contain(source_image.convert("RGB"), (cell_width, cell_height))
        score_data = load_score_overlay_data(image_path)
        prepared = add_score_badge(
            prepared,
            score_data.get("score"),
            enabled=show_score_badge,
            score_breakdown=score_data.get("score_breakdown"),
            weights=score_data.get("scoring_weights"),
            raw_score=score_data.get("raw_score"),
        )

        paste_x = offset_x + (cell_width - prepared.width) // 2
        paste_y = offset_y + (cell_height - prepared.height) // 2
        canvas.paste(prepared, (paste_x, paste_y))

    canvas.save(output, format=sheet_config["output_format"], quality=sheet_config["output_quality"])
    return output


def compose_pending_sheets(config: dict, logger, allow_partial: bool | None = None) -> list[Path]:
    selected_dir = Path(config["paths"]["output_selected"])
    sheets_dir = Path(config["paths"]["output_sheets"])
    archive_dir = Path(config["paths"]["output_archive"]) / "sheets"
    sheet_config = config["sheet"]
    photos_per_sheet = sheet_config["photos_per_sheet"]
    partial_enabled = sheet_config.get("allow_partial_sheet", False) if allow_partial is None else allow_partial
    partial_minimum = min(sheet_config.get("min_photos_to_compose", photos_per_sheet), photos_per_sheet)

    selected_files = sorted(selected_dir.glob("*.jpg"), key=lambda path: (path.stat().st_mtime, path.name.lower()))
    generated_sheets: list[Path] = []

    while len(selected_files) >= photos_per_sheet:
        batch = selected_files[:photos_per_sheet]
        sheet_name = f"sheet_{datetime.now():%Y%m%d_%H%M%S_%f}"
        output_path = sheets_dir / f"{sheet_name}.jpg"
        compose_sheet(batch, output_path, sheet_config)

        sheet_archive_dir = archive_dir / sheet_name
        sheet_archive_dir.mkdir(parents=True, exist_ok=True)
        for file_path in batch:
            shutil.move(str(file_path), sheet_archive_dir / file_path.name)

        logger.info("Собран лист %s из %s фотографий", output_path.name, len(batch))
        generated_sheets.append(output_path)
        selected_files = selected_files[photos_per_sheet:]

    if partial_enabled and selected_files and len(selected_files) >= partial_minimum:
        batch = selected_files[:]
        sheet_name = f"sheet_partial_{datetime.now():%Y%m%d_%H%M%S_%f}"
        output_path = sheets_dir / f"{sheet_name}.jpg"
        compose_sheet(batch, output_path, sheet_config)

        sheet_archive_dir = archive_dir / sheet_name
        sheet_archive_dir.mkdir(parents=True, exist_ok=True)
        for file_path in batch:
            shutil.move(str(file_path), sheet_archive_dir / file_path.name)

        logger.info("Собран тестовый частичный лист %s из %s фотографий", output_path.name, len(batch))
        generated_sheets.append(output_path)
    elif selected_files and not generated_sheets:
        logger.info(
            "Для листа пока недостаточно фото: есть %s, нужно %s (тестовый минимум %s)",
            len(selected_files),
            photos_per_sheet,
            partial_minimum,
        )

    return generated_sheets


def load_score_overlay_data(image_path: Path) -> dict[str, object]:
    config = _load_runtime_config()
    if config and photo_metadata_enabled(config):
        metadata_path = build_photo_metadata_path(config, image_path)
        if metadata_path.exists():
            return _read_metadata(metadata_path)

    report_data = _load_score_data_from_reports(image_path)
    if report_data["score"] is not None:
        return report_data

    return {"score": None, "score_breakdown": None, "scoring_weights": None, "raw_score": None}


def _load_runtime_config() -> dict | None:
    from config_utils import load_config

    try:
        return load_config()
    except Exception:
        return None


def _read_metadata(metadata_path: Path) -> dict[str, object]:
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        metadata = None
    if isinstance(metadata, dict):
        return {
            "score": float(metadata["score"]) if isinstance(metadata.get("score"), (int, float)) else None,
            "score_breakdown": metadata.get("score_breakdown"),
            "scoring_weights": metadata.get("scoring_weights"),
            "raw_score": float(metadata["raw_score"]) if isinstance(metadata.get("raw_score"), (int, float)) else None,
        }
    return {"score": None, "score_breakdown": None, "scoring_weights": None, "raw_score": None}


def _load_score_data_from_reports(image_path: Path) -> dict[str, object]:

    log_dir = image_path.parents[1] / "logs"
    if not log_dir.exists():
        return {"score": None, "score_breakdown": None, "scoring_weights": None, "raw_score": None}

    for report_path in sorted(log_dir.glob("ser*_report.json")):
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        if report.get("selected_file") == image_path.name and isinstance(report.get("best_score"), (int, float)):
            source_file = report.get("source_file")
            if not isinstance(source_file, str):
                name_parts = image_path.name.split("_", 1)
                source_file = name_parts[1] if len(name_parts) == 2 else image_path.name

            photo_entry = None
            for photo in report.get("photos", []):
                if isinstance(photo, dict) and photo.get("file_name") == source_file:
                    photo_entry = photo
                    break

            return {
                "score": float(report["best_score"]),
                "score_breakdown": photo_entry.get("score_breakdown") if isinstance(photo_entry, dict) else None,
                "scoring_weights": photo_entry.get("scoring_weights") if isinstance(photo_entry, dict) else None,
                "raw_score": float(photo_entry["raw_score"])
                if isinstance(photo_entry, dict) and isinstance(photo_entry.get("raw_score"), (int, float))
                else None,
            }

    return {"score": None, "score_breakdown": None, "scoring_weights": None, "raw_score": None}
