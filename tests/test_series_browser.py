from __future__ import annotations

import json
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from series_browser import (
    _MonitorState,
    _render_series_list,
    _render_series_detail,
    _start_monitoring,
    load_all_series,
    rescue_batch,
    rescue_photo,
)


def _make_config(tmp: str) -> dict:
    root = Path(tmp)
    return {
        "paths": {
            "input_folder": str(root / "incoming"),
            "output_selected": str(root / "selected"),
            "log_dir": str(root / "logs"),
        },
        "network": {"auto_sync_sheets": False, "output_path": ""},
    }


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
            self.assertEqual(result[0]["series"], "SER002")
            self.assertEqual(result[1]["series"], "SER001")

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
            incoming = Path(tmp) / "incoming"
            incoming.mkdir()
            (incoming / "a.jpg").write_bytes(b"photo_a")
            (incoming / "b.jpg").write_bytes(b"photo_b")

            selected = Path(tmp) / "selected"
            config = _make_config(tmp)
            photos = [
                {"path": str(incoming / "a.jpg"), "series": "SER001"},
                {"path": str(incoming / "b.jpg"), "series": "SER002"},
            ]

            copied = rescue_batch(photos, selected, config)

            self.assertEqual(len(copied), 2)
            self.assertTrue((selected / "SER001_a.jpg").exists())
            self.assertTrue((selected / "SER002_b.jpg").exists())

    def test_batch_skips_already_copied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            incoming = Path(tmp) / "incoming"
            incoming.mkdir()
            (incoming / "a.jpg").write_bytes(b"photo_a")

            selected = Path(tmp) / "selected"
            selected.mkdir()
            (selected / "SER001_a.jpg").write_bytes(b"already_there")

            config = _make_config(tmp)
            photos = [{"path": str(incoming / "a.jpg"), "series": "SER001"}]

            copied = rescue_batch(photos, selected, config)

            self.assertEqual(len(copied), 0)
            # Original file is untouched
            self.assertEqual((selected / "SER001_a.jpg").read_bytes(), b"already_there")

    def test_batch_skips_missing_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            selected = Path(tmp) / "selected"
            config = _make_config(tmp)
            photos = [{"path": "/no/such/file.jpg", "series": "SER001"}]

            copied = rescue_batch(photos, selected, config)

            self.assertEqual(len(copied), 0)


class MonitoringStartupTests(unittest.TestCase):
    def tearDown(self) -> None:
        _MonitorState.running = False
        _MonitorState.thread = None
        _MonitorState.observer = None
        _MonitorState.series_count = 0
        _MonitorState.last_activity = ""
        _MonitorState.error = ""

    def test_start_monitoring_reports_import_error_instead_of_raising(self) -> None:
        original_import = __import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "watcher":
                raise ImportError("watcher missing in build")
            return original_import(name, globals, locals, fromlist, level)

        with mock.patch("builtins.__import__", side_effect=fake_import):
            _start_monitoring({})

        self.assertFalse(_MonitorState.is_active())
        self.assertIn("watcher missing in build", _MonitorState.error)


class SeriesDetailRenderTests(unittest.TestCase):
    def test_series_detail_contains_lightbox_payload_and_controls(self) -> None:
        series = {
            "series": "SER001",
            "selected_file": "SER001_frame1.jpg",
            "photos": [
                {
                    "file_name": "frame1.jpg",
                    "file_path": "C:/tmp/frame1.jpg",
                    "score": 82.5,
                    "subject_present": True,
                    "person_fallback": False,
                    "score_breakdown": {
                        "quality_gate": "pass",
                        "head_readability": 0.91,
                        "head_pose": 0.88,
                        "head_sharpness": 0.77,
                        "head_exposure": 0.66,
                        "readable_count": 0.50,
                        "frame_quality": 0.72,
                        "smile_bonus": 1.0,
                    },
                    "scoring_weights": {
                        "head_readability": 30,
                        "head_pose": 15,
                        "head_sharpness": 20,
                        "head_exposure": 15,
                        "readable_count": 10,
                        "frame_quality": 8,
                        "smile_bonus": 2,
                    },
                    "readable_face_count": 2,
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            selected_dir = Path(tmp) / "selected"
            selected_dir.mkdir()
            (selected_dir / "SER001_frame1.jpg").write_bytes(b"\xff\xd8fake jpeg")
            html = _render_series_detail(series, selected_dir, _make_config(tmp))

        self.assertIn('data-lightbox-group="series-SER001"', html)
        self.assertIn('data-lightbox-payload=', html)
        self.assertIn('class="lightbox-nav prev"', html)
        self.assertIn('id="debug-toggle"', html)
        self.assertIn('Улыбка', html)

    def test_series_detail_history_disables_rescue_for_missing_files(self) -> None:
        series = {
            "series": "SER099",
            "selected_file": "",
            "photos": [
                {
                    "file_name": "missing.jpg",
                    "file_path": "C:/missing/missing.jpg",
                    "score": 22.0,
                    "subject_present": True,
                    "person_fallback": False,
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            html = _render_series_detail(series, Path(tmp) / "selected", _make_config(tmp))

        self.assertIn("История серии", html)
        self.assertIn("Исходник очищен", html)
        self.assertNotIn('action="/rescue"', html)
        self.assertNotIn("Спасти фото</button>", html)


class SeriesListRenderTests(unittest.TestCase):
    def test_series_list_contains_refresh_button_and_cleanup_explanation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            html = _render_series_list([], _make_config(tmp), page=1, filter_status="")

        self.assertIn('refreshPage()', html)
        self.assertIn('Отчёты серий, логи, аннотации (убирает карточки серий)', html)

    def test_navbar_has_archive_button_and_disk_indicator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            html = _render_series_list([], _make_config(tmp), page=1, filter_status="")

        self.assertIn('openZipModal()', html)
        self.assertIn('disk-indicator', html)

    def test_zip_modal_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            html = _render_series_list([], _make_config(tmp), page=1, filter_status="")

        self.assertIn('id="zip-modal"', html)
        self.assertIn('zip-preset', html)
        self.assertIn('runZipExport()', html)

    def test_working_view_hides_history_but_history_tab_keeps_access(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _make_config(tmp)
            incoming = Path(config["paths"]["input_folder"])
            incoming.mkdir(parents=True)
            live_path = incoming / "live.jpg"
            live_path.write_bytes(b"\xff\xd8live")

            series = [
                {
                    "series": "SER001",
                    "status": "selected",
                    "selected_file": "",
                    "photos": [{"file_name": "live.jpg", "file_path": str(live_path)}],
                },
                {
                    "series": "SER002",
                    "status": "selected",
                    "selected_file": "",
                    "photos": [{"file_name": "gone.jpg", "file_path": "C:/missing/gone.jpg"}],
                },
            ]

            working_html = _render_series_list(series, config, page=1, filter_status="")
            history_html = _render_series_list(series, config, page=1, filter_status="history")

        self.assertIn("Рабочие (1)", working_html)
        self.assertNotIn("/series/SER002", working_html)
        self.assertIn("/series/SER002", history_html)
        self.assertIn("Файлы очищены", history_html)
        self.assertNotIn("/nearby/SER002", history_html)


if __name__ == "__main__":
    unittest.main()
