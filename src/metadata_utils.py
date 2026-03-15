from __future__ import annotations

import hashlib
from pathlib import Path


def photo_metadata_enabled(config: dict) -> bool:
    return bool(config.get("output", {}).get("write_photo_metadata_json", False))


def get_photo_metadata_dir(config: dict) -> Path:
    return Path(config["paths"]["photo_metadata_dir"])


def build_photo_metadata_path(config: dict, image_path: str | Path) -> Path:
    image = Path(image_path)
    digest = hashlib.sha1(str(image.resolve()).encode("utf-8")).hexdigest()[:12]
    return get_photo_metadata_dir(config) / f"{image.stem}__{digest}.json"
