from __future__ import annotations

import sys
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from badge_utils import add_score_badge


class BadgeUtilsTests(unittest.TestCase):
    def test_badge_is_not_drawn_when_disabled(self) -> None:
        image = Image.new("RGB", (240, 320), color=(120, 140, 160))

        result = add_score_badge(image, 42.0, enabled=False)

        self.assertEqual(list(result.getdata()), list(image.getdata()))

    def test_score_table_is_drawn_with_breakdown(self) -> None:
        image = Image.new("RGB", (800, 1200), color=(120, 140, 160))
        result = add_score_badge(
            image,
            42.0,
            enabled=True,
            score_breakdown={
                "person_present": 1.0,
                "sharpness": 0.6,
                "exposure": 0.8,
            },
            weights={
                "person_present": 40,
                "sharpness": 35,
                "exposure": 25,
            },
        )

        self.assertNotEqual(list(result.getdata()), list(image.getdata()))


if __name__ == "__main__":
    unittest.main()
