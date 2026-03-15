from __future__ import annotations

from datetime import datetime
import shutil
from pathlib import Path

from PIL import Image

from analyzer import analyze_photo
from badge_utils import add_score_badge
from config_utils import save_json
from image_utils import save_image
from metadata_utils import build_photo_metadata_path, photo_metadata_enabled


def process_series(
    series_files: list[Path],
    series_index: int,
    face_analyzer,
    config: dict,
    logger,
    remove_source_files: bool = False,
    save_annotations: bool = False,
) -> dict:
    if not series_files:
        return {"series_index": series_index, "status": "empty", "selected_file": None, "series_size": 0}

    series_name = f"SER{series_index:03d}"
    results: list[dict] = []
    annotations_dir = Path(config["paths"]["annotated_dir"]) / series_name

    logger.info("Обработка серии %s: %s файлов", series_name, len(series_files))

    for photo_path in series_files:
        metrics, annotated = analyze_photo(photo_path, face_analyzer, config)
        results.append(metrics)

        if save_annotations:
            save_image(annotations_dir / f"{photo_path.stem}_annotated.jpg", annotated)

    occupied_results = [result for result in results if result.get("subject_present")]
    report_path = Path(config["paths"]["log_dir"]) / f"{series_name.lower()}_report.json"
    show_score_badge = bool(config.get("output", {}).get("show_score_badge", True))
    write_photo_metadata = photo_metadata_enabled(config)

    for result in results:
        result["scoring_weights"] = config["scoring_weights"]

    if not occupied_results:
        rejected_dir = build_rejected_dir(
            Path(config["paths"]["output_rejected"]),
            series_name,
            series_files,
            "empty",
        )
        _save_rejected_files(
            series_files,
            results,
            rejected_dir,
            remove_source_files,
            show_score_badge=show_score_badge,
            config=config,
        )
        save_json({"series": series_name, "status": "discarded_empty", "photos": results}, report_path)
        logger.info("Серия %s отброшена как пустая", series_name)
        return {"series_index": series_index, "status": "discarded_empty", "selected_file": None, "series_size": len(series_files)}

    best_result = max(occupied_results, key=lambda item: item["score"])
    best_path = Path(best_result["file_path"])
    selected_output = Path(config["paths"]["output_selected"]) / f"{series_name}_{best_path.name}"
    shutil.copy2(best_path, selected_output)

    if write_photo_metadata:
        save_json(
            {
                "series": series_name,
                "selected_file": selected_output.name,
                "score": best_result["score"],
                "source_file": best_path.name,
                "score_breakdown": best_result.get("score_breakdown", {}),
                "scoring_weights": best_result.get("scoring_weights"),
            },
            build_photo_metadata_path(config, selected_output),
        )

    rejected_results = [result for result in results if result["file_name"] != best_path.name]
    rejected_source_files = [path for path in series_files if path.name != best_path.name]
    if rejected_source_files:
        rejected_dir = build_rejected_dir(
            Path(config["paths"]["output_rejected"]),
            series_name,
            rejected_source_files,
            "rejected",
        )
        _save_rejected_files(
            rejected_source_files,
            rejected_results,
            rejected_dir,
            remove_source_files,
            show_score_badge=show_score_badge,
            config=config,
        )

    save_json(
        {
            "series": series_name,
            "status": "selected",
            "selected_file": selected_output.name,
            "source_file": best_path.name,
            "best_score": best_result["score"],
            "photos": results,
        },
        report_path,
    )

    logger.info("Серия %s: выбрано %s со score=%.2f", series_name, selected_output.name, best_result["score"])
    return {
        "series_index": series_index,
        "status": "selected",
        "selected_file": str(selected_output),
        "series_size": len(series_files),
        "best_score": best_result["score"],
    }


def build_rejected_dir(base_dir: Path, series_name: str, series_files: list[Path], suffix: str) -> Path:
    sorted_files = sorted(series_files, key=lambda path: (path.stat().st_mtime, path.name.lower()))
    reference_path = sorted_files[0]
    reference_datetime = datetime.fromtimestamp(reference_path.stat().st_ctime)
    day_folder = base_dir / reference_datetime.strftime("%Y-%m-%d")
    folder_name = f"{reference_datetime:%Y%m%d_%H%M%S}__{series_name}__{suffix}"
    return day_folder / folder_name


def export_result_status(result: dict) -> str:
    return "rejected" if result.get("subject_present") else "discarded_empty"


def _save_rejected_files(
    series_files: list[Path],
    results: list[dict],
    target_dir: Path,
    remove_source_files: bool,
    show_score_badge: bool = True,
    config: dict | None = None,
) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    results_by_name = {result["file_name"]: result for result in results}
    write_photo_metadata = bool(config and photo_metadata_enabled(config))

    for source_path in series_files:
        target_path = target_dir / source_path.name
        result = results_by_name.get(source_path.name, {})
        score = result.get("score")

        with Image.open(source_path) as source_image:
            badged = add_score_badge(
                source_image.convert("RGB"),
                float(score) if isinstance(score, (int, float)) else None,
                enabled=show_score_badge,
                score_breakdown=result.get("score_breakdown"),
                weights=result.get("scoring_weights"),
            )
            badged.save(target_path, format="JPEG", quality=95)

        if remove_source_files and source_path.exists():
            source_path.unlink()

        if write_photo_metadata:
            save_json(
                {
                    "file_name": source_path.name,
                    "score": score,
                    "status": export_result_status(result),
                    "score_breakdown": result.get("score_breakdown", {}),
                    "scoring_weights": result.get("scoring_weights"),
                },
                build_photo_metadata_path(config, target_path),
            )
