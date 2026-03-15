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


# ---------------------------------------------------------------------------
# Layer A — Occupancy Gate
# ---------------------------------------------------------------------------

def compute_occupancy(metrics: dict) -> bool:
    """Is the chair occupied (face or fallback person detected)?"""
    return bool(metrics.get("subject_present", False))


# ---------------------------------------------------------------------------
# Layer B — Quality Gate
# ---------------------------------------------------------------------------

def compute_quality_gate(metrics: dict, thresholds: dict) -> str:
    """Reject obvious junk before fine ranking.

    Returns ``"pass"``, ``"weak"`` or ``"fail"``.
    """
    faces = metrics.get("faces", [])

    # Use face-level sharpness/brightness when available, else overall
    if faces:
        sharpness = mean(f.get("sharpness", 0.0) for f in faces)
        brightness = mean(f.get("brightness", 0.0) for f in faces)
    else:
        sharpness = metrics.get("overall_sharpness", 0.0)
        brightness = metrics.get("overall_brightness", 0.0)

    fail_sharp = thresholds.get("quality_fail_sharpness", 15.0)
    fail_bright_lo = thresholds.get("quality_fail_brightness_low", 30.0)
    fail_bright_hi = thresholds.get("quality_fail_brightness_high", 245.0)
    weak_sharp = thresholds.get("quality_weak_sharpness", 40.0)

    if sharpness < fail_sharp:
        return "fail"
    if brightness < fail_bright_lo or brightness > fail_bright_hi:
        return "fail"
    if sharpness < weak_sharp:
        return "weak"
    return "pass"


# ---------------------------------------------------------------------------
# Layer C — Ranking Score
# ---------------------------------------------------------------------------

def compute_ranking_score(
    metrics: dict,
    weights: dict,
    thresholds: dict,
) -> tuple[float, dict[str, float]]:
    """Compare viable frames within a series and rank them.

    Components (default weights summing to 100):
      head_readability  30 — aggregate face readability
      head_pose         15 — preference for frontal views
      head_sharpness    20 — local sharpness of face region
      head_exposure     15 — local brightness centered around target
      readable_count    10 — bonus for multiple readable faces
      frame_quality      8 — overall image sharpness + brightness
      smile_bonus        2 — weak positive-expression bonus
    """
    faces = metrics.get("faces", [])
    detection_type = metrics.get("detection_type", "empty")

    # --- per-face aggregates ---
    if faces:
        head_readability = mean(f.get("readability", 0.0) for f in faces)

        # Pose: prefer |yaw| close to 0
        pose_tolerance = thresholds.get("pose_yaw_tolerance", 45.0)
        pose_scores = []
        for f in faces:
            yaw = abs(f.get("yaw", 180.0))
            if yaw >= pose_tolerance:
                pose_scores.append(0.0)
            else:
                pose_scores.append(1.0 - yaw / pose_tolerance)
        head_pose = mean(pose_scores)

        head_sharpness = mean(
            normalize_range(
                f.get("sharpness", 0.0),
                thresholds.get("min_head_sharpness", 30.0),
                thresholds.get("good_head_sharpness", 180.0),
            )
            for f in faces
        )
        head_exposure = mean(
            centered_score(
                f.get("brightness", 0.0),
                thresholds.get("target_head_brightness", 145.0),
                thresholds.get("head_brightness_tolerance", 90.0),
            )
            for f in faces
        )

        # Readable count: bonus scales with absolute number of readable faces
        # 1 readable = 0.5, 2 readable = 0.8, 3+ = 1.0
        readable = metrics.get("readable_face_count", 0)
        if readable <= 0:
            readable_count = 0.0
        elif readable == 1:
            readable_count = 0.5
        elif readable == 2:
            readable_count = 0.8
        else:
            readable_count = 1.0

        # Smile bonus
        smile_threshold = thresholds.get("smile_mouth_ratio_threshold", 0.3)
        smile_scores = []
        for f in faces:
            mr = f.get("mouth_ratio", 0.0)
            smile_scores.append(clamp(mr / smile_threshold) if smile_threshold > 0 else 0.0)
        smile_bonus = mean(smile_scores) if smile_scores else 0.0
    else:
        head_readability = 0.0
        head_pose = 0.0
        head_sharpness = 0.0
        head_exposure = 0.0
        readable_count = 0.0
        smile_bonus = 0.0

    # Frame quality — overall image
    frame_sharpness = normalize_range(
        metrics.get("overall_sharpness", 0.0),
        thresholds.get("min_frame_sharpness", 50.0),
        thresholds.get("good_frame_sharpness", 250.0),
    )
    frame_brightness = centered_score(
        metrics.get("overall_brightness", 0.0),
        thresholds.get("target_head_brightness", 145.0),
        thresholds.get("head_brightness_tolerance", 90.0),
    )
    frame_quality = 0.6 * frame_sharpness + 0.4 * frame_brightness

    parts = {
        "head_readability": head_readability,
        "head_pose": head_pose,
        "head_sharpness": head_sharpness,
        "head_exposure": head_exposure,
        "readable_count": readable_count,
        "frame_quality": frame_quality,
        "smile_bonus": smile_bonus,
    }

    # Weighted sum
    total = 0.0
    for key, weight in weights.items():
        total += parts.get(key, 0.0) * float(weight)

    # Fallback ceiling: fallback frames cannot outscore decent face frames
    if detection_type == "fallback":
        ceiling = thresholds.get("fallback_score_ceiling", 45.0)
        total = min(total, ceiling)

    return total, parts


# ---------------------------------------------------------------------------
# Public API — kept compatible with analyzer.py / selector.py
# ---------------------------------------------------------------------------

def compute_overall_score(
    metrics: dict,
    weights: dict,
    thresholds: dict,
) -> tuple[float, dict[str, float]]:
    """Three-layer scoring: occupancy → quality → ranking.

    Returns ``(score, parts_dict)`` where ``parts_dict`` includes
    all sub-scores plus ``occupied`` (bool→float) and ``quality_gate``.
    """
    occupied = compute_occupancy(metrics)
    if not occupied:
        return 0.0, {
            "occupied": 0.0,
            "quality_gate": "fail",
            "head_readability": 0.0,
            "head_pose": 0.0,
            "head_sharpness": 0.0,
            "head_exposure": 0.0,
            "readable_count": 0.0,
            "frame_quality": 0.0,
            "smile_bonus": 0.0,
        }

    quality_gate = compute_quality_gate(metrics, thresholds)
    ranking, parts = compute_ranking_score(metrics, weights, thresholds)

    # Apply quality gate ceilings
    if quality_gate == "fail":
        ranking = min(ranking, 10.0)
    elif quality_gate == "weak":
        ranking = min(ranking, 55.0)

    parts["occupied"] = 1.0
    parts["quality_gate"] = quality_gate
    return ranking, parts
