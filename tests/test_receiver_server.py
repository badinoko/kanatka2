"""Tests for receiver HTTP server."""
from __future__ import annotations

import json
import sys
import unittest
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "receiver"))


class TestReceiverServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from receiver_server import create_receiver_server
        from receiver_watcher import SheetQueue
        cls.queue = SheetQueue(max_items=50)
        cls.server = create_receiver_server(cls.queue, port=18788)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_root_returns_html(self):
        conn = HTTPConnection("127.0.0.1", 18788)
        conn.request("GET", "/")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        body = resp.read().decode()
        self.assertIn("html", body.lower())
        conn.close()

    def test_api_sheets_returns_json(self):
        conn = HTTPConnection("127.0.0.1", 18788)
        conn.request("GET", "/api/sheets")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        data = json.loads(resp.read())
        self.assertIn("sheets", data)
        conn.close()

    def test_404_for_unknown_path(self):
        conn = HTTPConnection("127.0.0.1", 18788)
        conn.request("GET", "/nonexistent")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 404)
        conn.close()


if __name__ == "__main__":
    unittest.main()
