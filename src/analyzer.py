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

    # Determine detection type and compute per-face readability
    if faces:
        detection_type = "face"
    elif person_fallback:
        detection_type = "fallback"
    else:
        detection_type = "empty"

    thresholds = config.get("thresholds", {})
    readability_min_conf = thresholds.get("readability_min_confidence", 0.4)
    readability_max_yaw = thresholds.get("readability_max_yaw", 55.0)
    readability_max_pitch = thresholds.get("readability_max_pitch", 40.0)
    readable_min_score = thresholds.get("readable_face_min_score", 0.3)

    readable_face_count = 0
    for face in faces:
        face["readability"] = _compute_face_readability(
            face, readability_min_conf, readability_max_yaw, readability_max_pitch,
        )
        if face["readability"] >= readable_min_score:
            readable_face_count += 1

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
        "detection_type": detection_type,
        "readable_face_count": readable_face_count,
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
    metrics["score_breakdown"] = {
        key: round(value, 3) if isinstance(value, (int, float)) else value
        for key, value in parts.items()
    }
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


def _compute_face_readability(
    face: dict,
    min_confidence: float = 0.4,
    max_yaw: float = 55.0,
    max_pitch: float = 40.0,
) -> float:
    """Aggregate readability score for a single face (0.0 – 1.0).

    Combines confidence, head pose (yaw/pitch within readable range),
    and local sharpness into a single number.
    """
    confidence = face.get("confidence", 0.0)
    yaw = abs(face.get("yaw", 180.0))
    pitch = abs(face.get("pitch", 180.0))
    sharpness = face.get("sharpness", 0.0)

    # Confidence component: 0 if below threshold, linear up to 1
    if confidence < min_confidence:
        conf_score = 0.0
    else:
        conf_score = min(1.0, (confidence - min_confidence) / max(0.01, 1.0 - min_confidence))

    # Pose component: 1.0 for frontal, falling off toward max_yaw/max_pitch
    if yaw >= max_yaw or pitch >= max_pitch:
        pose_score = 0.0
    else:
        yaw_score = 1.0 - (yaw / max_yaw)
        pitch_score = 1.0 - (pitch / max_pitch)
        pose_score = min(yaw_score, pitch_score)

    # Sharpness component: normalized 0..1 (30 = min, 180 = good)
    sharp_score = max(0.0, min(1.0, (sharpness - 30.0) / 150.0))

    # Weighted combination
    return 0.40 * conf_score + 0.35 * pose_score + 0.25 * sharp_score
