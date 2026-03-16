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

from sheet_composer import _load_score_data_from_reports


class SheetMetadataFallbackTests(unittest.TestCase):
    def test_selected_image_uses_series_report_without_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            selected_dir = root / "selected"
            logs_dir = root / "logs"
            selected_dir.mkdir()
            logs_dir.mkdir()

            image_path = selected_dir / "S_1_example.jpg"
            image_path.write_bytes(b"stub")

            report = {
                "series": "S_1",
                "status": "selected",
                "selected_file": "S_1_example.jpg",
                "source_file": "example.jpg",
                "best_score": 44.5,
                "photos": [
                    {
                        "file_name": "example.jpg",
                        "score_breakdown": {"face_count": 0.33},
                        "scoring_weights": {"face_count": 30},
                        "raw_score": 5.0,
                    }
                ],
            }
            (logs_dir / "s_1_report.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")

            data = _load_score_data_from_reports(image_path)

            self.assertEqual(data["score"], 44.5)
            self.assertEqual(data["score_breakdown"], {"face_count": 0.33})
            self.assertEqual(data["scoring_weights"], {"face_count": 30})
            self.assertEqual(data["raw_score"], 5.0)


if __name__ == "__main__":
    unittest.main()
