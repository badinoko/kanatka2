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
    """Subject presence is now determined by face detection only."""

    def setUp(self) -> None:
        self.weights = {"person_present": 40, "sharpness": 35, "exposure": 25}
        self.thresholds = {
            "min_head_sharpness": 30.0,
            "good_head_sharpness": 180.0,
            "target_head_brightness": 145.0,
            "head_brightness_tolerance": 90.0,
        }

    def test_face_detected_means_subject_present(self) -> None:
        _, parts = compute_overall_score(
            {"face_count": 1, "faces": [{"sharpness": 100.0, "brightness": 140.0}]},
            self.weights,
            self.thresholds,
        )
        self.assertEqual(parts["person_present"], 1.0)

    def test_no_face_means_no_subject(self) -> None:
        _, parts = compute_overall_score(
            {"face_count": 0, "faces": []},
            self.weights,
            self.thresholds,
        )
        self.assertEqual(parts["person_present"], 0.0)


if __name__ == "__main__":
    unittest.main()
