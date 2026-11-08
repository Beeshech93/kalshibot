"""Unit tests for Technical Analysis Indicators (EMA 9, 21, 50, RSI 14, MACD, Volume)."""

import unittest
import numpy as np
import pandas as pd
from app.technical_analysis import TechnicalAnalysis


class TestIndicators(unittest.TestCase):
    """Verifies precision and behavior of technical indicator algorithms."""

    def setUp(self):
        # Generate 60 synthetic candle steps with an uptrend
        np.random.seed(42)
        prices = [50000.0]
        for _ in range(60):
            prices.append(prices[-1] + np.random.uniform(5, 50))

        self.uptrend_candles = []
        for i in range(1, 61):
            p = prices[i]
            self.uptrend_candles.append({
                "timestamp": f"2026-11-08T00:{i:02d}:00Z",
                "open": p - 10,
                "high": p + 15,
                "low": p - 12,
                "close": p,
                "volume": 100.0 + (i * 2)
            })

    def test_ema_calculation(self):
        series = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0])
        ema3 = TechnicalAnalysis.calculate_ema(series, 3)
        self.assertEqual(len(ema3), len(series))
        self.assertGreater(ema3.iloc[-1], ema3.iloc[0])

    def test_rsi_bounds_and_trending(self):
        series = pd.Series(range(100, 200))  # strictly rising series
        rsi = TechnicalAnalysis.calculate_rsi(series, period=14)
        # Rising prices should result in high RSI (close to 100)
        self.assertGreater(rsi.iloc[-1], 70.0)
        self.assertLessEqual(rsi.iloc[-1], 100.0)

        # Falling series
        falling_series = pd.Series(range(200, 100, -1))
        rsi_falling = TechnicalAnalysis.calculate_rsi(falling_series, period=14)
        self.assertLess(rsi_falling.iloc[-1], 30.0)
        self.assertGreaterEqual(rsi_falling.iloc[-1], 0.0)

    def test_macd_calculation(self):
        series = pd.Series(range(100, 160))
        macd_l, signal_l, hist = TechnicalAnalysis.calculate_macd(series)
        self.assertEqual(len(macd_l), len(series))
        self.assertEqual(len(signal_l), len(series))
        self.assertEqual(len(hist), len(series))

    def test_analyze_candles_uptrend(self):
        snapshot = TechnicalAnalysis.analyze_candles(self.uptrend_candles, "15m")
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.timeframe, "15m")
        self.assertIn(snapshot.trend, ("BULLISH", "MILD_BULLISH"))
        self.assertGreater(snapshot.ema_9, snapshot.ema_50)
        self.assertTrue(snapshot.volume_confirmed)

    def test_insufficient_candles(self):
        # Fewer than 30 candles must safely return None without throwing exception
        short_candles = self.uptrend_candles[:10]
        snapshot = TechnicalAnalysis.analyze_candles(short_candles, "15m")
        self.assertIsNone(snapshot)


if __name__ == "__main__":
    unittest.main()
