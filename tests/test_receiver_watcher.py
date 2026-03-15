"""Tests for receiver folder watcher."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "receiver"))


class TestSheetQueue(unittest.TestCase):
    def test_add_and_list(self):
        from receiver_watcher import SheetQueue
        q = SheetQueue(max_items=50)
        q.add(Path("sheet_001.jpg"))
        q.add(Path("sheet_002.jpg"))
        items = q.get_latest()
        self.assertEqual(len(items), 2)

    def test_max_items_limit(self):
        from receiver_watcher import SheetQueue
        q = SheetQueue(max_items=3)
        for i in range(5):
            q.add(Path(f"sheet_{i:03d}.jpg"))
        items = q.get_latest()
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0].name, "sheet_004.jpg")

    def test_no_duplicates(self):
        from receiver_watcher import SheetQueue
        q = SheetQueue(max_items=50)
        q.add(Path("sheet_001.jpg"))
        q.add(Path("sheet_001.jpg"))
        items = q.get_latest()
        self.assertEqual(len(items), 1)

    def test_scan_existing_folder(self):
        from receiver_watcher import SheetQueue
        q = SheetQueue(max_items=50)
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(3):
                (Path(tmpdir) / f"sheet_{i:03d}.jpg").write_bytes(b"\xff\xd8")
            (Path(tmpdir) / "readme.txt").write_text("ignore me")
            q.scan_folder(Path(tmpdir))
        items = q.get_latest()
        self.assertEqual(len(items), 3)


if __name__ == "__main__":
    unittest.main()
