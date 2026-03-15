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
            "person_present": 40,
            "sharpness": 35,
            "exposure": 25,
        }
        self.thresholds = {
            "min_head_sharpness": 30.0,
            "good_head_sharpness": 180.0,
            "target_head_brightness": 145.0,
            "head_brightness_tolerance": 90.0,
        }

    def test_no_person_gives_zero_score(self) -> None:
        score, parts = compute_overall_score(
            {"face_count": 0, "faces": []},
            self.weights,
            self.thresholds,
        )
        self.assertEqual(parts["person_present"], 0.0)
        self.assertEqual(parts["sharpness"], 0.0)
        self.assertEqual(parts["exposure"], 0.0)
        self.assertEqual(score, 0.0)

    def test_good_face_gives_high_score(self) -> None:
        score, parts = compute_overall_score(
            {
                "face_count": 1,
                "faces": [{"sharpness": 150.0, "brightness": 145.0}],
            },
            self.weights,
            self.thresholds,
        )
        self.assertEqual(parts["person_present"], 1.0)
        self.assertGreater(parts["sharpness"], 0.7)
        self.assertGreater(parts["exposure"], 0.9)
        self.assertGreater(score, 80.0)

    def test_blurry_face_has_low_sharpness(self) -> None:
        _, parts = compute_overall_score(
            {
                "face_count": 1,
                "faces": [{"sharpness": 35.0, "brightness": 145.0}],
            },
            self.weights,
            self.thresholds,
        )
        self.assertLess(parts["sharpness"], 0.1)

    def test_extreme_brightness_has_low_exposure(self) -> None:
        _, parts = compute_overall_score(
            {
                "face_count": 1,
                "faces": [{"sharpness": 150.0, "brightness": 250.0}],
            },
            self.weights,
            self.thresholds,
        )
        self.assertLess(parts["exposure"], 0.0001)


if __name__ == "__main__":
    unittest.main()
