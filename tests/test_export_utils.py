from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from export_utils import create_results_zip, sync_to_network


class CreateResultsZipTests(unittest.TestCase):
    def test_creates_zip_with_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            selected = Path(tmp) / "selected"
            sheets = Path(tmp) / "sheets"
            selected.mkdir()
            sheets.mkdir()
            (selected / "photo1.jpg").write_bytes(b"img1")
            (sheets / "sheet1.jpg").write_bytes(b"sheet1")

            config = {
                "paths": {
                    "output_selected": str(selected),
                    "output_sheets": str(sheets),
                }
            }

            # Override desktop to temp
            import export_utils
            original_home = Path.home
            Path.home = staticmethod(lambda: Path(tmp))
            try:
                (Path(tmp) / "Desktop").mkdir(exist_ok=True)
                result = create_results_zip(config)
                self.assertTrue(result.exists())
                self.assertTrue(result.name.startswith("kanatka_results_"))

                with zipfile.ZipFile(result) as zf:
                    names = zf.namelist()
                    self.assertIn("selected/photo1.jpg", names)
                    self.assertIn("sheets/sheet1.jpg", names)
            finally:
                Path.home = original_home

    def test_raises_on_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            selected = Path(tmp) / "selected"
            sheets = Path(tmp) / "sheets"
            selected.mkdir()
            sheets.mkdir()

            config = {
                "paths": {
                    "output_selected": str(selected),
                    "output_sheets": str(sheets),
                }
            }

            with self.assertRaises(ValueError):
                create_results_zip(config)


class SyncToNetworkTests(unittest.TestCase):
    def test_copies_new_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            target = Path(tmp) / "target"
            source.mkdir()
            target.mkdir()
            (source / "a.jpg").write_bytes(b"aaa")
            (source / "b.jpg").write_bytes(b"bbb")

            count = sync_to_network(source, str(target))

            self.assertEqual(count, 2)
            self.assertTrue((target / "a.jpg").exists())
            self.assertTrue((target / "b.jpg").exists())

    def test_skips_existing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            target = Path(tmp) / "target"
            source.mkdir()
            target.mkdir()
            (source / "a.jpg").write_bytes(b"new")
            (target / "a.jpg").write_bytes(b"old")

            count = sync_to_network(source, str(target))

            self.assertEqual(count, 0)
            self.assertEqual((target / "a.jpg").read_bytes(), b"old")

    def test_handles_missing_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            (source / "a.jpg").write_bytes(b"data")

            count = sync_to_network(source, str(Path(tmp) / "nonexistent"))

            self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
