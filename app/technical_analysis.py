"""Technical Analysis module implementing EMA (9, 21, 50), RSI (14), MACD (12, 26, 9),
Volume Confirmation & Anomaly detection across multiple timeframes (1m, 5m, 15m).
"""

from dataclasses import dataclass
import logging
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

logger = logging.getLogger("TechnicalAnalysis")


@dataclass
class IndicatorSnapshot:
    timeframe: str
    close_price: float
    ema_9: float
    ema_21: float
    ema_50: float
    rsi_14: float
    macd_line: float
    macd_signal: float
    macd_histogram: float
    volume: float
    avg_volume: float
    volume_confirmed: bool
    volume_abnormal: bool
    trend: str  # BULLISH, BEARISH, NEUTRAL
    momentum: str  # STRONG_UP, WEAK_UP, NEUTRAL, WEAK_DOWN, STRONG_DOWN

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timeframe": self.timeframe,
            "close_price": round(self.close_price, 2),
            "ema_9": round(self.ema_9, 2),
            "ema_21": round(self.ema_21, 2),
            "ema_50": round(self.ema_50, 2),
            "rsi_14": round(self.rsi_14, 2),
            "macd_line": round(self.macd_line, 2),
            "macd_signal": round(self.macd_signal, 2),
            "macd_histogram": round(self.macd_histogram, 2),
            "volume": round(self.volume, 4),
            "avg_volume": round(self.avg_volume, 4),
            "volume_confirmed": self.volume_confirmed,
            "volume_abnormal": self.volume_abnormal,
            "trend": self.trend,
            "momentum": self.momentum
        }


class TechnicalAnalysis:
    """Computes technical indicators and validates conditions on closed OHLCV candles."""

    @staticmethod
    def calculate_ema(series: pd.Series, period: int) -> pd.Series:
        """Calculates Exponential Moving Average."""
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
        """Calculates Relative Strength Index (RSI 14) using Wilder's smoothing."""
        delta = series.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)

        # Wilder's exponential smoothing
        avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

        # Handle zero loss (RSI = 100) and zero gain (RSI = 0)
        rsi = pd.Series(index=series.index, dtype=float)
        both_zero = (avg_gain == 0) & (avg_loss == 0)
        zero_loss = (avg_loss == 0) & (avg_gain > 0)
        zero_gain = (avg_gain == 0) & (avg_loss > 0)
        normal = (avg_loss > 0) & (avg_gain > 0)

        rsi[both_zero] = 50.0
        rsi[zero_loss] = 100.0
        rsi[zero_gain] = 0.0

        rs = avg_gain[normal] / avg_loss[normal]
        rsi[normal] = 100.0 - (100.0 / (1.0 + rs))

        return rsi.fillna(50.0)

    @staticmethod
    def calculate_macd(
        series: pd.Series,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """Calculates MACD (12, 26, 9): macd_line, signal_line, histogram."""
        fast_ema = series.ewm(span=fast_period, adjust=False).mean()
        slow_ema = series.ewm(span=slow_period, adjust=False).mean()
        macd_line = fast_ema - slow_ema
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    @classmethod
    def analyze_candles(cls, candles: List[Dict[str, Any]], timeframe: str) -> Optional[IndicatorSnapshot]:
        """Calculates all required indicators for a given set of closed candles."""
        if not candles or len(candles) < 30:
            logger.warning(f"Insufficient candles ({len(candles) if candles else 0}) for {timeframe} analysis. Need >= 30.")
            return None

        df = pd.DataFrame(candles)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna().reset_index(drop=True)
        if len(df) < 30:
            return None

        close = df["close"]
        vol = df["volume"]

        # EMAs
        ema9_s = cls.calculate_ema(close, 9)
        ema21_s = cls.calculate_ema(close, 21)
        ema50_s = cls.calculate_ema(close, 50)

        # RSI
        rsi_s = cls.calculate_rsi(close, 14)

        # MACD
        fast_ema = close.ewm(span=12, adjust=False).mean()
        slow_ema = close.ewm(span=26, adjust=False).mean()
        macd_line_s = fast_ema - slow_ema
        signal_line_s = macd_line_s.ewm(span=9, adjust=False).mean()
        hist_s = macd_line_s - signal_line_s

        # Volume
        avg_vol_20 = vol.rolling(window=min(20, len(vol)), min_periods=5).mean()

        # Latest closed values
        c_price = float(close.iloc[-1])
        ema9 = float(ema9_s.iloc[-1])
        ema21 = float(ema21_s.iloc[-1])
        ema50 = float(ema50_s.iloc[-1]) if len(close) >= 50 else float(ema21)
        rsi = float(rsi_s.iloc[-1])
        macd_l = float(macd_line_s.iloc[-1])
        macd_sig = float(signal_line_s.iloc[-1])
        macd_h = float(hist_s.iloc[-1])
        curr_vol = float(vol.iloc[-1])
        avg_vol = float(avg_vol_20.iloc[-1]) if not np.isnan(avg_vol_20.iloc[-1]) else curr_vol

        # Volume flags
        volume_confirmed = curr_vol >= avg_vol
        volume_abnormal = curr_vol >= (avg_vol * 2.0)

        # Trend Determination
        if ema9 > ema21 and ema21 > ema50 and c_price > ema9:
            trend = "BULLISH"
        elif ema9 < ema21 and ema21 < ema50 and c_price < ema9:
            trend = "BEARISH"
        elif ema9 > ema21:
            trend = "MILD_BULLISH"
        elif ema9 < ema21:
            trend = "MILD_BEARISH"
        else:
            trend = "NEUTRAL"

        # Momentum Determination
        if macd_h > 0 and macd_l > macd_sig and rsi > 55:
            momentum = "STRONG_UP"
        elif macd_h > 0 or (rsi > 50 and macd_l > macd_sig):
            momentum = "WEAK_UP"
        elif macd_h < 0 and macd_l < macd_sig and rsi < 45:
            momentum = "STRONG_DOWN"
        elif macd_h < 0 or (rsi < 50 and macd_l < macd_sig):
            momentum = "WEAK_DOWN"
        else:
            momentum = "NEUTRAL"

        return IndicatorSnapshot(
            timeframe=timeframe,
            close_price=c_price,
            ema_9=ema9,
            ema_21=ema21,
            ema_50=ema50,
            rsi_14=rsi,
            macd_line=macd_l,
            macd_signal=macd_sig,
            macd_histogram=macd_h,
            volume=curr_vol,
            avg_volume=avg_vol,
            volume_confirmed=volume_confirmed,
            volume_abnormal=volume_abnormal,
            trend=trend,
            momentum=momentum
        )

    @classmethod
    def analyze_multi_timeframe(
        cls,
        mtf_candles: Dict[str, List[Dict[str, Any]]]
    ) -> Dict[str, Optional[IndicatorSnapshot]]:
        """Analyzes 1m, 5m, and 15m closed candle sets."""
        return {
            tf: cls.analyze_candles(candles, tf)
            for tf, candles in mtf_candles.items()
        }
