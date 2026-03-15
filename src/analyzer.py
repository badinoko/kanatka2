from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from badge_utils import add_score_badge
from face_utils import MediaPipeFaceAnalyzer
from image_utils import compute_brightness, compute_sharpness, read_image, resize_longest_side
from scorer import compute_overall_score


def analyze_photo(photo_path: str | Path, face_analyzer: MediaPipeFaceAnalyzer, config: dict) -> tuple[dict, object]:
    start_time = time.perf_counter()
    image = read_image(photo_path)
    resized, scale = resize_longest_side(image, config["processing"]["resize_longest_side"])

    face_start = time.perf_counter()
    faces = face_analyzer.analyze_faces(resized)
    face_seconds = time.perf_counter() - face_start

    # If no face found, try HOG person detection as fallback
    person_fallback = False
    if not faces:
        min_person_conf = float(config.get("thresholds", {}).get("min_person_confidence", 0.5))
        haar_config = config.get("haar_cascade", {})
        person_fallback = face_analyzer.detect_person(resized, min_confidence=min_person_conf, haar_config=haar_config)

    metrics = {
        "file_name": Path(photo_path).name,
        "file_path": str(Path(photo_path).resolve()),
        "image_width": resized.shape[1],
        "image_height": resized.shape[0],
        "resize_scale": scale,
        "face_count": len(faces),
        "faces": faces,
        "subject_present": len(faces) > 0 or person_fallback,
        "person_fallback": person_fallback,
        "overall_brightness": compute_brightness(resized),
        "overall_sharpness": compute_sharpness(resized),
        "timings": {
            "face_seconds": round(face_seconds, 4),
        },
    }

    score, parts = compute_overall_score(
        metrics,
        config["scoring_weights"],
        config["thresholds"],
    )
    metrics["score"] = round(score, 3)
    metrics["score_breakdown"] = {key: round(value, 3) for key, value in parts.items()}
    metrics["timings"]["total_seconds"] = round(time.perf_counter() - start_time, 4)

    annotated = draw_annotations(resized.copy(), metrics, config["scoring_weights"])
    return metrics, annotated


def draw_annotations(image, metrics: dict, scoring_weights: dict):
    for index, face in enumerate(metrics["faces"], start=1):
        x1, y1, x2, y2 = face["bbox"]
        cv2.rectangle(image, (x1, y1), (x2, y2), (0, 180, 0), 2)

        lines = [
            f"#{index} conf={face.get('confidence', 0.0):.2f}",
            f"yaw={face.get('yaw', 0.0):.1f} pitch={face.get('pitch', 0.0):.1f}",
            f"sharp={face.get('sharpness', 0.0):.1f}",
        ]

        text_y = max(y1 - 10, 18)
        for offset, line in enumerate(lines):
            cv2.putText(image, line, (x1, text_y + offset * 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(image, line, (x1, text_y + offset * 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (25, 25, 25), 1, cv2.LINE_AA)

    header = [
        f"score={metrics['score']:.2f}",
        f"faces={metrics['face_count']}",
        f"sharp={metrics['overall_sharpness']:.1f}",
        f"time={metrics['timings']['total_seconds']:.2f}s",
    ]

    for offset, line in enumerate(header):
        cv2.putText(image, line, (10, 24 + offset * 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(image, line, (10, 24 + offset * 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)

    pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    pil_image = add_score_badge(
        pil_image,
        metrics.get("score"),
        enabled=True,
        score_breakdown=metrics.get("score_breakdown"),
        weights=scoring_weights,
    )
    return cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
