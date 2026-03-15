from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from series_browser import load_all_series, rescue_batch, rescue_photo


class LoadAllSeriesTests(unittest.TestCase):
    def test_loads_reports_sorted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_dir = Path(tmp)
            (log_dir / "ser002_report.json").write_text(
                json.dumps({"series": "SER002", "status": "selected", "photos": []}),
                encoding="utf-8",
            )
            (log_dir / "ser001_report.json").write_text(
                json.dumps({"series": "SER001", "status": "discarded_empty", "photos": []}),
                encoding="utf-8",
            )

            result = load_all_series(log_dir)

            self.assertEqual(len(result), 2)
            self.assertEqual(result[0]["series"], "SER001")
            self.assertEqual(result[1]["series"], "SER002")

    def test_skips_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_dir = Path(tmp)
            (log_dir / "ser001_report.json").write_text("not json", encoding="utf-8")
            (log_dir / "ser002_report.json").write_text(
                json.dumps({"series": "SER002", "status": "selected", "photos": []}),
                encoding="utf-8",
            )

            result = load_all_series(log_dir)
            self.assertEqual(len(result), 1)

    def test_empty_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = load_all_series(Path(tmp))
            self.assertEqual(result, [])


class RescuePhotoTests(unittest.TestCase):
    def test_copies_with_series_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "photo.jpg"
            source.write_bytes(b"\xff\xd8fake jpeg")
            selected = Path(tmp) / "selected"

            dest = rescue_photo(source, selected, "SER005")

            self.assertTrue(dest.exists())
            self.assertEqual(dest.name, "SER005_photo.jpg")
            self.assertEqual(dest.read_bytes(), b"\xff\xd8fake jpeg")

    def test_creates_selected_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "img.jpg"
            source.write_bytes(b"data")
            selected = Path(tmp) / "new_dir" / "selected"

            dest = rescue_photo(source, selected, "SER001")

            self.assertTrue(selected.exists())
            self.assertTrue(dest.exists())


class RescueBatchTests(unittest.TestCase):
    def test_batch_copies_multiple_photos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inbox = Path(tmp) / "INBOX"
            inbox.mkdir()
            (inbox / "a.jpg").write_bytes(b"photo_a")
            (inbox / "b.jpg").write_bytes(b"photo_b")

            selected = Path(tmp) / "selected"
            config = {
                "paths": {"test_photos_folder": str(inbox)},
                "network": {"auto_sync_sheets": False, "output_path": ""},
            }
            photos = [
                {"path": str(inbox / "a.jpg"), "series": "SER001"},
                {"path": str(inbox / "b.jpg"), "series": "SER002"},
            ]

            copied = rescue_batch(photos, selected, config)

            self.assertEqual(len(copied), 2)
            self.assertTrue((selected / "SER001_a.jpg").exists())
            self.assertTrue((selected / "SER002_b.jpg").exists())

    def test_batch_skips_already_copied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inbox = Path(tmp) / "INBOX"
            inbox.mkdir()
            (inbox / "a.jpg").write_bytes(b"photo_a")

            selected = Path(tmp) / "selected"
            selected.mkdir()
            (selected / "SER001_a.jpg").write_bytes(b"already_there")

            config = {
                "paths": {"test_photos_folder": str(inbox)},
                "network": {"auto_sync_sheets": False, "output_path": ""},
            }
            photos = [{"path": str(inbox / "a.jpg"), "series": "SER001"}]

            copied = rescue_batch(photos, selected, config)

            self.assertEqual(len(copied), 0)
            # Original file is untouched
            self.assertEqual((selected / "SER001_a.jpg").read_bytes(), b"already_there")

    def test_batch_skips_missing_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            selected = Path(tmp) / "selected"
            config = {
                "paths": {"test_photos_folder": str(Path(tmp) / "nonexistent")},
                "network": {"auto_sync_sheets": False, "output_path": ""},
            }
            photos = [{"path": "/no/such/file.jpg", "series": "SER001"}]

            copied = rescue_batch(photos, selected, config)

            self.assertEqual(len(copied), 0)


if __name__ == "__main__":
    unittest.main()
