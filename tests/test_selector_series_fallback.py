from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from selector import export_result_status


class SelectorLogicTests(unittest.TestCase):
    def test_subject_present_result_is_rejected(self) -> None:
        self.assertEqual(export_result_status({"subject_present": True}), "rejected")

    def test_empty_result_is_discarded(self) -> None:
        self.assertEqual(export_result_status({"subject_present": False}), "discarded_empty")
        self.assertEqual(export_result_status({}), "discarded_empty")


if __name__ == "__main__":
    unittest.main()
