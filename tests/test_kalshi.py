"""Unit tests for Kalshi Client, Market Parser, and Series Fallback."""

import unittest
from unittest.mock import MagicMock, patch

from app.config import Settings
from app.kalshi_client import KalshiClient


class TestKalshiClient(unittest.TestCase):
    """Verifies Kalshi market data parsing, fallbacks, and error tolerance."""

    def setUp(self):
        self.settings = Settings(
            kalshi_target_series="KXBTC15M",
            kalshi_fallback_series=["KXBTCH", "KXBTCD"]
        )
        self.client = KalshiClient(self.settings)

    def test_dollars_to_cents_conversion(self):
        self.assertEqual(KalshiClient._dollars_to_cents("0.7500"), 75.0)
        self.assertEqual(KalshiClient._dollars_to_cents("0.2450"), 24.5)
        self.assertEqual(KalshiClient._dollars_to_cents(0.50), 50.0)
        self.assertIsNone(KalshiClient._dollars_to_cents(None))
        self.assertIsNone(KalshiClient._dollars_to_cents(""))

    def test_parse_market_valid(self):
        raw = {
            "ticker": "KXBTC15M-26NOV080215-15",
            "title": "BTC price up in next 15 mins?",
            "status": "active",
            "yes_bid_dollars": "0.7500",
            "yes_ask_dollars": "0.7600",
            "no_bid_dollars": "0.2400",
            "no_ask_dollars": "0.2500",
            "last_price_dollars": "0.7500",
            "floor_strike": 75720.52,
            "close_time": "2026-11-08T07:15:00Z",
            "rules_primary": "Test rules for settlement.",
            "rules_secondary": "",
            "volume_fp": "5000.0",
            "open_interest_fp": "1200.0"
        }

        parsed = self.client._parse_market(raw, "KXBTC15M")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["ticker"], "KXBTC15M-26NOV080215-15")
        self.assertEqual(parsed["yes_ask"], 76.0)
        self.assertEqual(parsed["no_ask"], 25.0)
        self.assertEqual(parsed["strike_price"], 75720.52)
        self.assertIn("Test rules", parsed["settlement_rules"])

    def test_series_fallback_mechanism(self):
        # Mock get_markets_for_series: returns empty for KXBTC15M, but returns valid for KXBTCH
        def mock_get_markets(series_ticker):
            if series_ticker == "KXBTC15M":
                return []
            elif series_ticker == "KXBTCH":
                return [{
                    "ticker": "KXBTCH-FALLBACK",
                    "title": "Hourly BTC",
                    "status": "active",
                    "yes_ask_dollars": "0.5000",
                    "no_ask_dollars": "0.5000",
                    "floor_strike": 75000.0,
                    "close_time": "2026-11-08T08:00:00Z"
                }]
            return []

        self.client.get_markets_for_series = MagicMock(side_effect=mock_get_markets)
        market, series_used = self.client.find_active_btc_market()

        self.assertIsNotNone(market)
        self.assertEqual(series_used, "KXBTCH")
        self.assertEqual(market["ticker"], "KXBTCH-FALLBACK")

    def test_handles_nonexistent_markets_gracefully(self):
        self.client.get_markets_for_series = MagicMock(return_value=[])
        market, series_used = self.client.find_active_btc_market()
        self.assertIsNone(market)
        self.assertEqual(series_used, "")


if __name__ == "__main__":
    unittest.main()
