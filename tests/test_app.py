"""Tests for start_server, start_browser, and launch_app."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure src/ is importable
_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)


class TestStartServer(unittest.TestCase):
    """start_server must start the HTTP server WITHOUT opening a browser."""

    @patch("series_browser.ThreadingHTTPServer")
    @patch("series_browser._kill_old_server")
    @patch("series_browser.webbrowser")
    def test_start_server_does_not_open_browser(self, mock_wb, mock_kill, mock_srv_cls):
        from series_browser import start_server

        mock_server = MagicMock()
        mock_srv_cls.return_value = mock_server

        thread = start_server({"paths": {}}, port=19999)

        mock_kill.assert_called_once_with(19999)
        mock_srv_cls.assert_called_once()
        mock_server.serve_forever.assert_not_called()  # called in thread
        mock_wb.open.assert_not_called()
        self.assertIsNotNone(thread)


class TestStartBrowser(unittest.TestCase):
    """start_browser must open a browser after starting the server."""

    @patch("series_browser.webbrowser")
    @patch("series_browser.ThreadingHTTPServer")
    @patch("series_browser._kill_old_server")
    def test_start_browser_opens_browser(self, mock_kill, mock_srv_cls, mock_wb):
        from series_browser import start_browser

        mock_server = MagicMock()
        mock_srv_cls.return_value = mock_server

        thread = start_browser({"paths": {}}, port=19999)

        mock_wb.open.assert_called_once_with("http://127.0.0.1:19999")
        self.assertIsNotNone(thread)


class TestLaunchApp(unittest.TestCase):
    """launch_app must be importable and callable."""

    def test_launch_app_is_callable(self):
        from app import launch_app
        self.assertTrue(callable(launch_app))


if __name__ == "__main__":
    unittest.main()
