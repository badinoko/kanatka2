import sys
import os
import unittest
import unittest.mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestComposeIfReady(unittest.TestCase):
    def _make_config(self, selected_dir="/nonexistent/dir", cols=2, rows=4):
        return {
            "paths": {"output_selected": selected_dir},
            "sheet": {"grid_columns": cols, "grid_rows": rows},
        }

    def test_returns_false_when_dir_does_not_exist(self):
        from sheet_composer import compose_if_ready
        config = self._make_config(selected_dir="/nonexistent/dir")
        result = compose_if_ready(config)
        self.assertFalse(result)

    def test_returns_false_when_too_few_photos(self):
        from sheet_composer import compose_if_ready
        import tempfile, pathlib
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._make_config(selected_dir=tmpdir, cols=2, rows=4)
            # capacity = 8, add 3 photos (below threshold)
            for i in range(3):
                pathlib.Path(tmpdir, f"photo_{i}.jpg").touch()
            with unittest.mock.patch("sheet_composer.list_jpeg_files", return_value=[
                pathlib.Path(tmpdir, f"photo_{i}.jpg") for i in range(3)
            ]):
                result = compose_if_ready(config)
        self.assertFalse(result)

    def test_returns_true_and_calls_compose_when_enough_photos(self):
        from sheet_composer import compose_if_ready
        import tempfile, pathlib
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self._make_config(selected_dir=tmpdir, cols=2, rows=4)
            photos = [pathlib.Path(tmpdir, f"photo_{i}.jpg") for i in range(8)]
            with unittest.mock.patch("sheet_composer.list_jpeg_files", return_value=photos):
                with unittest.mock.patch("sheet_composer.compose_pending_sheets") as mock_compose:
                    result = compose_if_ready(config)
        self.assertTrue(result)
        mock_compose.assert_called_once_with(config, logger=None)


if __name__ == "__main__":
    unittest.main()
