from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scorer import compute_overall_score


class ScorerLogicTests(unittest.TestCase):
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
            "min_frame_sharpness": 50.0,
            "good_frame_sharpness": 250.0,
            "target_head_brightness": 145.0,
            "head_brightness_tolerance": 90.0,
            "fallback_score_ceiling": 45.0,
            "quality_fail_sharpness": 15.0,
            "quality_fail_brightness_low": 30.0,
            "quality_fail_brightness_high": 245.0,
            "quality_weak_sharpness": 40.0,
            "readability_min_confidence": 0.4,
            "readability_max_yaw": 55.0,
            "readability_max_pitch": 40.0,
            "readable_face_min_score": 0.3,
            "pose_yaw_tolerance": 45.0,
            "smile_mouth_ratio_threshold": 0.3,
        }

    def _good_face(self, **overrides) -> dict:
        face = {
            "confidence": 0.9,
            "yaw": 5.0,
            "pitch": 3.0,
            "sharpness": 150.0,
            "brightness": 145.0,
            "readability": 0.8,
            "mouth_ratio": 0.1,
        }
        face.update(overrides)
        return face

    def _make_metrics(self, faces=None, fallback=False, **extra) -> dict:
        if faces is None:
            faces = []
        readable = sum(1 for f in faces if f.get("readability", 0) >= 0.3)
        m = {
            "face_count": len(faces),
            "faces": faces,
            "subject_present": len(faces) > 0 or fallback,
            "person_fallback": fallback and len(faces) == 0,
            "detection_type": "face" if faces else ("fallback" if fallback else "empty"),
            "readable_face_count": readable,
            "overall_sharpness": extra.get("overall_sharpness", 120.0),
            "overall_brightness": extra.get("overall_brightness", 140.0),
        }
        m.update(extra)
        return m

    # --- Occupancy ---

    def test_empty_chair_gives_zero_score(self) -> None:
        score, parts = compute_overall_score(
            self._make_metrics(),
            self.weights,
            self.thresholds,
        )
        self.assertEqual(score, 0.0)
        self.assertEqual(parts["occupied"], 0.0)

    # --- Fallback ceiling ---

    def test_fallback_score_capped(self) -> None:
        score, parts = compute_overall_score(
            self._make_metrics(fallback=True, overall_sharpness=200.0, overall_brightness=145.0),
            self.weights,
            self.thresholds,
        )
        self.assertGreater(score, 0.0)
        self.assertLessEqual(score, 45.0)

    # --- Face beats fallback ---

    def test_face_beats_fallback(self) -> None:
        face_score, _ = compute_overall_score(
            self._make_metrics([self._good_face()]),
            self.weights,
            self.thresholds,
        )
        fallback_score, _ = compute_overall_score(
            self._make_metrics(fallback=True, overall_sharpness=200.0, overall_brightness=145.0),
            self.weights,
            self.thresholds,
        )
        self.assertGreater(face_score, fallback_score)

    # --- Good face gives high score ---

    def test_good_face_gives_high_score(self) -> None:
        score, parts = compute_overall_score(
            self._make_metrics([self._good_face()]),
            self.weights,
            self.thresholds,
        )
        self.assertEqual(parts["occupied"], 1.0)
        self.assertGreater(parts["head_readability"], 0.5)
        self.assertGreater(score, 60.0)

    # --- Two faces beat one ---

    def test_two_faces_beat_one(self) -> None:
        one_score, _ = compute_overall_score(
            self._make_metrics([self._good_face()]),
            self.weights,
            self.thresholds,
        )
        two_score, _ = compute_overall_score(
            self._make_metrics([self._good_face(), self._good_face()]),
            self.weights,
            self.thresholds,
        )
        self.assertGreater(two_score, one_score)

    # --- Quality gate fail ---

    def test_quality_gate_fail_caps_score(self) -> None:
        blurry_face = self._good_face(sharpness=10.0)
        score, parts = compute_overall_score(
            self._make_metrics([blurry_face]),
            self.weights,
            self.thresholds,
        )
        self.assertEqual(parts["quality_gate"], "fail")
        self.assertLessEqual(score, 10.0)

    # --- Quality gate weak ---

    def test_quality_gate_weak_caps_score(self) -> None:
        marginal_face = self._good_face(sharpness=35.0)
        score, parts = compute_overall_score(
            self._make_metrics([marginal_face]),
            self.weights,
            self.thresholds,
        )
        self.assertEqual(parts["quality_gate"], "weak")
        self.assertLessEqual(score, 55.0)

    # --- Frontal beats profile ---

    def test_frontal_beats_profile(self) -> None:
        frontal_score, _ = compute_overall_score(
            self._make_metrics([self._good_face(yaw=5.0)]),
            self.weights,
            self.thresholds,
        )
        profile_score, _ = compute_overall_score(
            self._make_metrics([self._good_face(yaw=40.0)]),
            self.weights,
            self.thresholds,
        )
        self.assertGreater(frontal_score, profile_score)


if __name__ == "__main__":
    unittest.main()
