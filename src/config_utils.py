from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from runtime_env import prepare_runtime_environment


PROJECT_ROOT = prepare_runtime_environment()
DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.json")


def get_project_root() -> Path:
    return PROJECT_ROOT


def _resolve_path(value: str) -> str:
    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str((PROJECT_ROOT / path).resolve())


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    data = json.loads(path.read_text(encoding="utf-8"))

    for key, value in data.get("paths", {}).items():
        if isinstance(value, str):
            data["paths"][key] = _resolve_path(value)

    data["__config_path"] = str(path.resolve())
    return data


def ensure_runtime_directories(config: dict[str, Any]) -> None:
    for key in (
        "input_folder",
        "output_selected",
        "output_sheets",
        "output_archive",
        "output_discarded",
        "output_rejected",
        "photo_metadata_dir",
        "log_dir",
        "annotated_dir",
    ):
        Path(config["paths"][key]).mkdir(parents=True, exist_ok=True)


def save_json(data: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_config(config: dict[str, Any], config_path: str | Path | None = None) -> None:
    path = Path(config_path or config.get("__config_path") or DEFAULT_CONFIG_PATH)
    serialized = copy.deepcopy(config)
    serialized.pop("__config_path", None)

    for key, value in serialized.get("paths", {}).items():
        if not isinstance(value, str):
            continue

        path_value = Path(value)
        try:
            relative = path_value.resolve().relative_to(PROJECT_ROOT.resolve())
        except ValueError:
            serialized["paths"][key] = str(path_value)
        else:
            serialized["paths"][key] = relative.as_posix()

    path.write_text(json.dumps(serialized, ensure_ascii=False, indent=2), encoding="utf-8")
