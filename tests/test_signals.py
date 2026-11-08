"""Unit tests for Signal Engine, Decision Scoring, and Duplicate Prevention."""

import os
from pathlib import Path
import tempfile
import unittest

from app.database import Database
from app.performance import PerformanceTracker
from app.signal_engine import SignalEngine
from app.technical_analysis import IndicatorSnapshot


class TestSignals(unittest.TestCase):
    """Verifies signal generation rules, scoring logic, and database persistence."""

    def setUp(self):
        self.engine = SignalEngine(min_confidence=60.0)

        # Temporary in-memory or temp-file DB
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "test_signals.db"
        self.db = Database(self.db_path)
        self.perf = PerformanceTracker(self.db)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_bullish_signals_yes(self):
        # Create strong bullish snapshots
        snap_15m = IndicatorSnapshot(
            timeframe="15m",
            close_price=76000.0,
            ema_9=75800.0,
            ema_21=75500.0,
            ema_50=75000.0,
            rsi_14=62.0,
            macd_line=120.0,
            macd_signal=80.0,
            macd_histogram=40.0,
            volume=500.0,
            avg_volume=250.0,
            volume_confirmed=True,
            volume_abnormal=True,
            trend="BULLISH",
            momentum="STRONG_UP"
        )
        snap_5m = IndicatorSnapshot(
            timeframe="5m",
            close_price=76000.0,
            ema_9=75900.0,
            ema_21=75800.0,
            ema_50=75600.0,
            rsi_14=60.0,
            macd_line=50.0,
            macd_signal=30.0,
            macd_histogram=20.0,
            volume=150.0,
            avg_volume=100.0,
            volume_confirmed=True,
            volume_abnormal=False,
            trend="BULLISH",
            momentum="STRONG_UP"
        )
        mtf = {"15m": snap_15m, "5m": snap_5m, "1m": None}

        market = {
            "ticker": "KXBTC15M-TEST",
            "title": "BTC up in next 15 min?",
            "yes_ask": 55.0,
            "no_ask": 45.0,
            "strike_price": 75800.0,
            "seconds_remaining": 600,
            "time_remaining_str": "10m 00s"
        }

        decision = self.engine.evaluate(mtf, market, current_btc_price=76000.0)
        self.assertEqual(decision.signal_type, "YES")
        self.assertGreaterEqual(decision.confidence_score, 60.0)
        self.assertIn("alcista", decision.technical_justification.lower())

    def test_bearish_signals_no(self):
        # Create strong bearish snapshots
        snap_15m = IndicatorSnapshot(
            timeframe="15m",
            close_price=74000.0,
            ema_9=74200.0,
            ema_21=74500.0,
            ema_50=75000.0,
            rsi_14=38.0,
            macd_line=-120.0,
            macd_signal=-80.0,
            macd_histogram=-40.0,
            volume=500.0,
            avg_volume=250.0,
            volume_confirmed=True,
            volume_abnormal=True,
            trend="BEARISH",
            momentum="STRONG_DOWN"
        )
        snap_5m = IndicatorSnapshot(
            timeframe="5m",
            close_price=74000.0,
            ema_9=74100.0,
            ema_21=74300.0,
            ema_50=74600.0,
            rsi_14=36.0,
            macd_line=-50.0,
            macd_signal=-30.0,
            macd_histogram=-20.0,
            volume=150.0,
            avg_volume=100.0,
            volume_confirmed=True,
            volume_abnormal=False,
            trend="BEARISH",
            momentum="STRONG_DOWN"
        )
        mtf = {"15m": snap_15m, "5m": snap_5m, "1m": None}

        market = {
            "ticker": "KXBTC15M-TEST-BEAR",
            "title": "BTC down?",
            "yes_ask": 35.0,
            "no_ask": 65.0,
            "strike_price": 74500.0,
            "seconds_remaining": 600,
            "time_remaining_str": "10m 00s"
        }

        decision = self.engine.evaluate(mtf, market, current_btc_price=74000.0)
        self.assertEqual(decision.signal_type, "NO")
        self.assertGreaterEqual(decision.confidence_score, 60.0)

    def test_conflicted_signals_wait(self):
        # Bullish 15m but Bearish 5m and low volume
        snap_15m = IndicatorSnapshot(
            timeframe="15m",
            close_price=75000.0,
            ema_9=75050.0,
            ema_21=75000.0,
            ema_50=74950.0,
            rsi_14=50.0,
            macd_line=5.0,
            macd_signal=4.0,
            macd_histogram=1.0,
            volume=50.0,
            avg_volume=100.0,
            volume_confirmed=False,
            volume_abnormal=False,
            trend="NEUTRAL",
            momentum="NEUTRAL"
        )
        snap_5m = IndicatorSnapshot(
            timeframe="5m",
            close_price=74980.0,
            ema_9=74970.0,
            ema_21=75010.0,
            ema_50=75050.0,
            rsi_14=44.0,
            macd_line=-8.0,
            macd_signal=-2.0,
            macd_histogram=-6.0,
            volume=40.0,
            avg_volume=100.0,
            volume_confirmed=False,
            volume_abnormal=False,
            trend="BEARISH",
            momentum="WEAK_DOWN"
        )
        mtf = {"15m": snap_15m, "5m": snap_5m, "1m": None}

        market = {
            "ticker": "KXBTC15M-CONFLICT",
            "title": "BTC Market",
            "yes_ask": 50.0,
            "no_ask": 50.0,
            "strike_price": 75000.0,
            "seconds_remaining": 500,
            "time_remaining_str": "8m 20s"
        }

        decision = self.engine.evaluate(mtf, market, current_btc_price=75000.0)
        self.assertEqual(decision.signal_type, "WAIT")

    def test_critical_time_remaining_forces_wait(self):
        # Even with strong bullish setup, seconds_remaining < 90 must yield WAIT
        snap_15m = IndicatorSnapshot(
            timeframe="15m",
            close_price=76000.0,
            ema_9=75800.0,
            ema_21=75500.0,
            ema_50=75000.0,
            rsi_14=62.0,
            macd_line=120.0,
            macd_signal=80.0,
            macd_histogram=40.0,
            volume=500.0,
            avg_volume=250.0,
            volume_confirmed=True,
            volume_abnormal=True,
            trend="BULLISH",
            momentum="STRONG_UP"
        )
        snap_5m = IndicatorSnapshot(
            timeframe="5m",
            close_price=76000.0,
            ema_9=75900.0,
            ema_21=75800.0,
            ema_50=75600.0,
            rsi_14=60.0,
            macd_line=50.0,
            macd_signal=30.0,
            macd_histogram=20.0,
            volume=150.0,
            avg_volume=100.0,
            volume_confirmed=True,
            volume_abnormal=False,
            trend="BULLISH",
            momentum="STRONG_UP"
        )
        mtf = {"15m": snap_15m, "5m": snap_5m, "1m": None}

        market_expiring = {
            "ticker": "KXBTC15M-EXPIRING",
            "title": "BTC Market",
            "yes_ask": 80.0,
            "no_ask": 20.0,
            "strike_price": 75800.0,
            "seconds_remaining": 45,  # < 90 seconds
            "time_remaining_str": "0m 45s"
        }

        decision = self.engine.evaluate(mtf, market_expiring, current_btc_price=76000.0)
        self.assertEqual(decision.signal_type, "WAIT")
        self.assertIn("crítico", decision.technical_justification.lower())

    def test_duplicate_signal_prevention(self):
        ticker = "KXBTC15M-DUPTEST"
        self.assertFalse(self.db.has_recent_signal(ticker, within_minutes=14))

        # Insert signal
        self.db.insert_signal(
            market_ticker=ticker,
            btc_price=75000.0,
            contract_price=50.0,
            signal_type="YES",
            indicators={"rsi": 60},
            confidence_score=75.0,
            reference_price=74800.0,
            technical_justification="Test signal"
        )

        # Immediate check should now detect the recent signal
        self.assertTrue(self.db.has_recent_signal(ticker, within_minutes=14))

    def test_performance_calculation_ignores_pending(self):
        # Insert 3 signals: 1 WIN, 1 LOSS, 1 PENDING
        sig1 = self.db.insert_signal("MKT1", 75000, 50, "YES", {}, 80, 74000, "sig1")
        sig2 = self.db.insert_signal("MKT2", 75000, 50, "NO", {}, 80, 76000, "sig2")
        sig3 = self.db.insert_signal("MKT3", 75000, 50, "YES", {}, 80, 74000, "sig3")

        # Evaluate sig1 as WIN, sig2 as LOSS, leave sig3 as PENDING
        self.db.update_signal_outcome(sig1, "WIN", 76000, "YES", "Hit target")
        self.db.update_signal_outcome(sig2, "LOSS", 77000, "YES", "Missed")

        stats = self.perf.calculate_stats()
        self.assertEqual(stats.total_signals, 3)
        self.assertEqual(stats.wins, 1)
        self.assertEqual(stats.losses, 1)
        self.assertEqual(stats.pending_evaluations, 1)
        self.assertEqual(stats.evaluated_signals, 2)
        # Win rate should be 1 / 2 = 50.0%, NOT 1 / 3!
        self.assertEqual(stats.win_rate_percent, 50.0)


if __name__ == "__main__":
    unittest.main()

