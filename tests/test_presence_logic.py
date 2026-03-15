from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scorer import compute_overall_score


class PresenceLogicTests(unittest.TestCase):
    """Occupancy gate: face or fallback means occupied."""

    def setUp(self) -> None:
        self.weights = {
            "head_readability": 30,
            "head_pose": 15,
            "head_sharpness": 20,
            "head_exposure": 15,
            "readable_count": 10,
            "frame_quality": 8,
            "smile_bonus": 2,
        }
        self.thresholds = {
            "min_head_sharpness": 30.0,
            "good_head_sharpness": 180.0,
            "target_head_brightness": 145.0,
            "head_brightness_tolerance": 90.0,
            "min_frame_sharpness": 50.0,
            "good_frame_sharpness": 250.0,
            "fallback_score_ceiling": 45.0,
            "quality_fail_sharpness": 15.0,
            "quality_fail_brightness_low": 30.0,
            "quality_fail_brightness_high": 245.0,
            "quality_weak_sharpness": 40.0,
            "pose_yaw_tolerance": 45.0,
            "smile_mouth_ratio_threshold": 0.3,
        }

    def test_face_detected_means_occupied(self) -> None:
        _, parts = compute_overall_score(
            {
                "face_count": 1,
                "faces": [{"sharpness": 100.0, "brightness": 140.0, "confidence": 0.9, "yaw": 0.0, "pitch": 0.0, "readability": 0.7, "mouth_ratio": 0.1}],
                "subject_present": True,
                "person_fallback": False,
                "detection_type": "face",
                "readable_face_count": 1,
                "overall_sharpness": 120.0,
                "overall_brightness": 140.0,
            },
            self.weights,
            self.thresholds,
        )
        self.assertEqual(parts["occupied"], 1.0)

    def test_no_face_no_fallback_means_empty(self) -> None:
        score, parts = compute_overall_score(
            {
                "face_count": 0,
                "faces": [],
                "subject_present": False,
                "person_fallback": False,
                "detection_type": "empty",
                "readable_face_count": 0,
                "overall_sharpness": 120.0,
                "overall_brightness": 140.0,
            },
            self.weights,
            self.thresholds,
        )
        self.assertEqual(parts["occupied"], 0.0)
        self.assertEqual(score, 0.0)

    def test_fallback_means_occupied(self) -> None:
        score, parts = compute_overall_score(
            {
                "face_count": 0,
                "faces": [],
                "subject_present": True,
                "person_fallback": True,
                "detection_type": "fallback",
                "readable_face_count": 0,
                "overall_sharpness": 120.0,
                "overall_brightness": 140.0,
            },
            self.weights,
            self.thresholds,
        )
        self.assertEqual(parts["occupied"], 1.0)
        self.assertGreater(score, 0.0)


if __name__ == "__main__":
    unittest.main()
