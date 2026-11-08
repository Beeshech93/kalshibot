"""Unit tests for the Flask Web Dashboard API endpoints."""

import unittest
from dashboard.app import app


class TestDashboard(unittest.TestCase):
    """Verifies that web dashboard endpoints respond correctly."""

    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_index_route(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"BTC SCALPING AI", resp.data)

    def test_api_overview(self):
        resp = self.client.get("/api/overview")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("status", data)
        self.assertEqual(data["status"], "ONLINE")
        self.assertIn("performance", data)

    def test_api_candles(self):
        resp = self.client.get("/api/candles?timeframe=15m&limit=10")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("candles", data)

    def test_api_signals(self):
        resp = self.client.get("/api/signals")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("signals", data)

    def test_api_performance(self):
        resp = self.client.get("/api/performance")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("win_rate_percent", data)


if __name__ == "__main__":
    unittest.main()

