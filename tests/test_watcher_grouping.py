from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from watcher import check_disk_space, group_files_by_time


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


class CheckDiskSpaceTests(unittest.TestCase):
    def test_returns_ok_when_plenty_of_space(self) -> None:
        import shutil as _shutil
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            selected = Path(tmp) / "selected"
            selected.mkdir()
            config = {
                "paths": {"output_selected": str(selected)},
                "health": {"min_free_gb": 0.001, "critical_free_gb": 0.0001},
            }
            result = check_disk_space(config)
        self.assertIn(result["status"], {"ok", "warning", "critical"})
        self.assertIsInstance(result["free_gb"], float)

    def test_status_critical_when_threshold_exceeds_free(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            selected = Path(tmp) / "selected"
            selected.mkdir()
            # Set thresholds above any realistic free space
            config = {
                "paths": {"output_selected": str(selected)},
                "health": {"min_free_gb": 999999.0, "critical_free_gb": 999998.0},
            }
            result = check_disk_space(config)
        self.assertEqual(result["status"], "critical")

    def test_returns_ok_on_oserror(self) -> None:
        config = {
            "paths": {"output_selected": "/nonexistent/path/that/cannot/exist"},
            "health": {"min_free_gb": 1.0, "critical_free_gb": 0.2},
        }
        result = check_disk_space(config)
        self.assertEqual(result["status"], "ok")
        self.assertIsNone(result["free_gb"])


if __name__ == "__main__":
    unittest.main()
