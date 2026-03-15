from __future__ import annotations

from statistics import mean


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def normalize_range(value: float, lower: float, upper: float) -> float:
    if upper <= lower:
        return 0.0
    return clamp((value - lower) / (upper - lower))


def centered_score(value: float, target: float, tolerance: float) -> float:
    if tolerance <= 0:
        return 0.0
    distance = abs(value - target)
    return clamp(1.0 - (distance / tolerance))


def compute_overall_score(
    metrics: dict,
    weights: dict,
    thresholds: dict,
) -> tuple[float, dict[str, float]]:
    faces = metrics.get("faces", [])
    person_present = bool(metrics.get("subject_present", len(faces) > 0))

    if faces:
        # Score by face quality
        sharpness_score = mean(
            normalize_range(
                face.get("sharpness", 0.0),
                thresholds["min_head_sharpness"],
                thresholds["good_head_sharpness"],
            )
            for face in faces
        )
        exposure_score = mean(
            centered_score(
                face.get("brightness", 0.0),
                thresholds["target_head_brightness"],
                thresholds["head_brightness_tolerance"],
            )
            for face in faces
        )
    elif person_present:
        # Person detected by HOG but no face — score by overall image quality
        sharpness_score = normalize_range(
            metrics.get("overall_sharpness", 0.0),
            thresholds.get("min_frame_sharpness", 50.0),
            thresholds.get("good_frame_sharpness", 250.0),
        )
        exposure_score = centered_score(
            metrics.get("overall_brightness", 0.0),
            thresholds["target_head_brightness"],
            thresholds["head_brightness_tolerance"],
        )
    else:
        sharpness_score = 0.0
        exposure_score = 0.0

    parts = {
        "person_present": 1.0 if person_present else 0.0,
        "sharpness": sharpness_score,
        "exposure": exposure_score,
    }

    total_score = 0.0
    for key, weight in weights.items():
        total_score += parts.get(key, 0.0) * float(weight)

    return total_score, parts
