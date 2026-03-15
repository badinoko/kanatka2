from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def read_image(image_path: str | Path) -> np.ndarray:
    path = Path(image_path)
    buffer = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Не удалось прочитать изображение: {path}")
    return image


def save_image(image_path: str | Path, image: np.ndarray, quality: int = 95) -> None:
    path = Path(image_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    extension = path.suffix.lower() or ".jpg"

    params: list[int] = []
    if extension in {".jpg", ".jpeg"}:
        params = [cv2.IMWRITE_JPEG_QUALITY, quality]

    success, encoded = cv2.imencode(extension, image, params)
    if not success:
        raise ValueError(f"Не удалось сохранить изображение: {path}")
    encoded.tofile(path)


def resize_longest_side(image: np.ndarray, max_side: int) -> tuple[np.ndarray, float]:
    height, width = image.shape[:2]
    longest_side = max(height, width)
    if longest_side <= max_side:
        return image.copy(), 1.0

    scale = max_side / float(longest_side)
    new_size = (max(int(width * scale), 1), max(int(height * scale), 1))
    resized = cv2.resize(image, new_size, interpolation=cv2.INTER_AREA)
    return resized, scale


def compute_brightness(image: np.ndarray) -> float:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(gray.mean())


def compute_sharpness(image: np.ndarray) -> float:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def crop_image(image: np.ndarray, bbox: tuple[int, int, int, int], padding_ratio: float = 0.0) -> np.ndarray:
    x1, y1, x2, y2 = bbox
    width = x2 - x1
    height = y2 - y1
    pad_x = int(width * padding_ratio)
    pad_y = int(height * padding_ratio)

    x1 = max(0, x1 - pad_x)
    y1 = max(0, y1 - pad_y)
    x2 = min(image.shape[1], x2 + pad_x)
    y2 = min(image.shape[0], y2 + pad_y)
    return image[y1:y2, x1:x2]


def list_jpeg_files(folder_path: str | Path) -> list[Path]:
    folder = Path(folder_path)
    return sorted(
        [
            path
            for path in folder.iterdir()
            if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg"}
        ],
        key=lambda path: (path.stat().st_mtime, path.name.lower()),
    )
