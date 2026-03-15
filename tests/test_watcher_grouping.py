from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from watcher import group_files_by_time


class GroupFilesByTimeTests(unittest.TestCase):
    def test_groups_by_creation_time_gap(self) -> None:
        files = [Path("b.jpg"), Path("c.jpg"), Path("a.jpg")]
        creation_times = {
            "a.jpg": 100.0,
            "b.jpg": 101.9,
            "c.jpg": 104.5,
        }

        with patch("watcher.get_file_creation_time", side_effect=lambda path: creation_times[path.name]):
            groups = group_files_by_time(files, max_gap_seconds=2.0)

        self.assertEqual([[path.name for path in group] for group in groups], [["a.jpg", "b.jpg"], ["c.jpg"]])

    def test_keeps_all_files_together_when_gap_within_threshold(self) -> None:
        files = [Path("frame3.jpg"), Path("frame1.jpg"), Path("frame2.jpg")]
        creation_times = {
            "frame1.jpg": 10.0,
            "frame2.jpg": 11.0,
            "frame3.jpg": 12.0,
        }

        with patch("watcher.get_file_creation_time", side_effect=lambda path: creation_times[path.name]):
            groups = group_files_by_time(files, max_gap_seconds=2.0)

        self.assertEqual(len(groups), 1)
        self.assertEqual([path.name for path in groups[0]], ["frame1.jpg", "frame2.jpg", "frame3.jpg"])


if __name__ == "__main__":
    unittest.main()
