"""Technical Analysis module implementing EMA (9, 21, 50), RSI (14), MACD (12, 26, 9),
Volume Confirmation & Anomaly detection across multiple timeframes (1m, 5m, 15m).
Pure-Python implementation with optional pandas acceleration.
"""

from dataclasses import dataclass
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import pandas as pd
except ImportError:
    pd = None

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


def _to_list(series: Any) -> Tuple[List[float], bool]:
    """Converts a pd.Series or list to List[float], returns (list, is_pandas)."""
    if pd is not None and isinstance(series, pd.Series):
        return [float(x) for x in series.tolist()], True
    return [float(x) for x in series], False


class TechnicalAnalysis:
    """Computes technical indicators and validates conditions on closed OHLCV candles."""

    @staticmethod
    def calculate_ema(series: Any, period: int) -> Any:
        """Calculates Exponential Moving Average."""
        vals, is_pd = _to_list(series)
        if not vals:
            res: List[float] = []
        else:
            alpha = 2.0 / (period + 1.0)
            ema = [vals[0]]
            for v in vals[1:]:
                ema.append(alpha * v + (1.0 - alpha) * ema[-1])
            res = ema

        if is_pd and pd is not None:
            return pd.Series(res, index=getattr(series, "index", None))
        return res

    @staticmethod
    def calculate_rsi(series: Any, period: int = 14) -> Any:
        """Calculates Relative Strength Index (RSI 14) using Wilder's smoothing."""
        vals, is_pd = _to_list(series)
        n = len(vals)
        if n == 0:
            res: List[float] = []
        elif n == 1:
            res = [50.0]
        else:
            deltas = [vals[i] - vals[i - 1] for i in range(1, n)]
            gains = [max(d, 0.0) for d in deltas]
            losses = [max(-d, 0.0) for d in deltas]

            alpha = 1.0 / period
            avg_gain = [gains[0]]
            avg_loss = [losses[0]]
            for g, l in zip(gains[1:], losses[1:]):
                avg_gain.append(alpha * g + (1.0 - alpha) * avg_gain[-1])
                avg_loss.append(alpha * l + (1.0 - alpha) * avg_loss[-1])

            rsi_vals = [50.0]  # Point 0
            for ag, al in zip(avg_gain, avg_loss):
                if ag == 0 and al == 0:
                    rsi_vals.append(50.0)
                elif al == 0:
                    rsi_vals.append(100.0)
                elif ag == 0:
                    rsi_vals.append(0.0)
                else:
                    rs = ag / al
                    rsi_vals.append(100.0 - (100.0 / (1.0 + rs)))
            res = rsi_vals

        if is_pd and pd is not None:
            return pd.Series(res, index=getattr(series, "index", None))
        return res

    @staticmethod
    def calculate_macd(
        series: Any,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9
    ) -> Tuple[Any, Any, Any]:
        """Calculates MACD: macd_line, signal_line, histogram."""
        vals, is_pd = _to_list(series)
        fast_ema = TechnicalAnalysis.calculate_ema(vals, fast_period)
        slow_ema = TechnicalAnalysis.calculate_ema(vals, slow_period)
        macd_line = [f - s for f, s in zip(fast_ema, slow_ema)]
        signal_line = TechnicalAnalysis.calculate_ema(macd_line, signal_period)
        histogram = [m - s for m, s in zip(macd_line, signal_line)]

        if is_pd and pd is not None:
            idx = getattr(series, "index", None)
            return pd.Series(macd_line, index=idx), pd.Series(signal_line, index=idx), pd.Series(histogram, index=idx)
        return macd_line, signal_line, histogram

    @classmethod
    def analyze_candles(cls, candles: List[Dict[str, Any]], timeframe: str) -> Optional[IndicatorSnapshot]:
        """Calculates all required indicators for a given set of closed candles."""
        if not candles or len(candles) < 30:
            logger.warning(f"Insufficient candles ({len(candles) if candles else 0}) for {timeframe} analysis. Need >= 30.")
            return None

        # Clean candles
        valid_candles = []
        for c in candles:
            try:
                cl = float(c["close"])
                vo = float(c.get("volume", 0.0))
                valid_candles.append((cl, vo))
            except (ValueError, KeyError, TypeError):
                continue

        if len(valid_candles) < 30:
            return None

        close = [c[0] for c in valid_candles]
        vol = [c[1] for c in valid_candles]

        # EMAs
        ema9_s = cls.calculate_ema(close, 9)
        ema21_s = cls.calculate_ema(close, 21)
        ema50_s = cls.calculate_ema(close, 50)

        # RSI
        rsi_s = cls.calculate_rsi(close, 14)

        # MACD
        macd_line_s, signal_line_s, hist_s = cls.calculate_macd(close, 12, 26, 9)

        # Volume SMA 20
        v_win = vol[-20:] if len(vol) >= 20 else vol
        avg_vol = sum(v_win) / len(v_win) if v_win else 1.0

        # Latest values
        c_price = close[-1]
        ema9 = ema9_s[-1]
        ema21 = ema21_s[-1]
        ema50 = ema50_s[-1]
        rsi = rsi_s[-1]
        macd_line = macd_line_s[-1]
        macd_signal = signal_line_s[-1]
        macd_hist = hist_s[-1]
        last_vol = vol[-1]

        # Trend logic
        if ema9 > ema21 > ema50:
            trend = "BULLISH"
        elif ema9 < ema21 < ema50:
            trend = "BEARISH"
        elif ema9 > ema50:
            trend = "MILD_BULLISH"
        elif ema9 < ema50:
            trend = "MILD_BEARISH"
        else:
            trend = "NEUTRAL"

        # Momentum logic
        if macd_hist > 0 and rsi > 55:
            momentum = "STRONG_UP" if rsi > 65 else "WEAK_UP"
        elif macd_hist < 0 and rsi < 45:
            momentum = "STRONG_DOWN" if rsi < 35 else "WEAK_DOWN"
        else:
            momentum = "NEUTRAL"

        # Volume checks
        volume_confirmed = last_vol >= (avg_vol * 0.95)
        volume_abnormal = last_vol >= (avg_vol * 2.0)

        return IndicatorSnapshot(
            timeframe=timeframe,
            close_price=c_price,
            ema_9=ema9,
            ema_21=ema21,
            ema_50=ema50,
            rsi_14=rsi,
            macd_line=macd_line,
            macd_signal=macd_signal,
            macd_histogram=macd_hist,
            volume=last_vol,
            avg_volume=avg_vol,
            volume_confirmed=volume_confirmed,
            volume_abnormal=volume_abnormal,
            trend=trend,
            momentum=momentum
        )

    @classmethod
    def analyze_multi_timeframe(cls, mtf_candles: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Optional[IndicatorSnapshot]]:
        """Analyzes 1m, 5m, 15m closed candles."""
        results: Dict[str, Optional[IndicatorSnapshot]] = {}
        for tf in ["1m", "5m", "15m"]:
            candles = mtf_candles.get(tf, [])
            results[tf] = cls.analyze_candles(candles, tf)
        return results
