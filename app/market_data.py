"""Market Data provider for BTC/USDT spot candles and ticker prices."""

from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, List, Optional
import requests

from app.database import Database

logger = logging.getLogger("MarketData")


class MarketDataManager:
    """Fetches real-time BTC/USDT price and multi-timeframe closed candles."""

    BINANCE_URL = "https://api.binance.com/api/v3"
    BINANCE_FALLBACK_URL = "https://data-api.binance.vision/api/v3"
    COINBASE_URL = "https://api.exchange.coinbase.com/products/BTC-USD"

    TIMEFRAME_MAP_BINANCE = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m"
    }

    TIMEFRAME_MAP_COINBASE = {
        "1m": 60,
        "5m": 300,
        "15m": 900
    }

    def __init__(self, db: Optional[Database] = None):
        self.db = db
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "BTC-Scalping-AI/1.0",
            "Accept": "application/json"
        })

    def get_current_btc_price(self) -> Optional[float]:
        """Fetches the current live spot price of BTC/USDT."""
        # Try Binance Primary
        for base in [self.BINANCE_URL, self.BINANCE_FALLBACK_URL]:
            try:
                resp = self.session.get(f"{base}/ticker/price?symbol=BTCUSDT", timeout=4)
                if resp.status_code == 200:
                    data = resp.json()
                    price = float(data.get("price", 0.0))
                    if price > 0:
                        return price
            except Exception as e:
                logger.debug(f"Binance spot price attempt failed: {e}")

        # Fallback to Coinbase
        try:
            resp = self.session.get(f"{self.COINBASE_URL}/ticker", timeout=4)
            if resp.status_code == 200:
                data = resp.json()
                price = float(data.get("price", 0.0))
                if price > 0:
                    return price
        except Exception as e:
            logger.warning(f"Coinbase spot price attempt failed: {e}")

        logger.error("All spot price sources failed.")
        return None

    def get_candles(self, timeframe: str = "15m", limit: int = 60, closed_only: bool = True) -> List[Dict[str, Any]]:
        """Fetches OHLCV candles for the given timeframe (1m, 5m, 15m).
        Ensures strictly closed candles are returned when closed_only=True.
        """
        candles = self._fetch_binance_candles(timeframe, limit=limit + (1 if closed_only else 0))
        if not candles:
            candles = self._fetch_coinbase_candles(timeframe, limit=limit + (1 if closed_only else 0))

        if not candles:
            logger.error(f"Failed to fetch {timeframe} candles from all sources.")
            return []

        # Sort ascending by timestamp
        candles.sort(key=lambda x: x["timestamp"])

        if closed_only and len(candles) > 1:
            # Check if the last candle is still open
            now_ts = int(time.time() * 1000)
            last = candles[-1]
            # If close_time is greater than current time, it's still open
            if last.get("close_time_ms", 0) > now_ts or True:
                # Discard the last unclosed candle to prevent lookahead / incomplete signal bias
                candles = candles[:-1]

        # Take requested limit
        result = candles[-limit:]

        # Optionally store in DB
        if self.db and result:
            try:
                self.db.insert_candles("BTCUSDT", timeframe, result)
            except Exception as e:
                logger.debug(f"Could not persist candles to DB: {e}")

        return result

    def get_multi_timeframe_candles(self, limit: int = 60) -> Dict[str, List[Dict[str, Any]]]:
        """Fetches closed candles for 1m, 5m, and 15m timeframes."""
        return {
            "1m": self.get_candles("1m", limit=limit, closed_only=True),
            "5m": self.get_candles("5m", limit=limit, closed_only=True),
            "15m": self.get_candles("15m", limit=limit, closed_only=True)
        }

    def _fetch_binance_candles(self, timeframe: str, limit: int = 60) -> List[Dict[str, Any]]:
        interval = self.TIMEFRAME_MAP_BINANCE.get(timeframe, "15m")
        for base in [self.BINANCE_URL, self.BINANCE_FALLBACK_URL]:
            try:
                url = f"{base}/klines"
                params = {"symbol": "BTCUSDT", "interval": interval, "limit": limit}
                resp = self.session.get(url, params=params, timeout=5)
                if resp.status_code == 200:
                    raw = resp.json()
                    candles = []
                    for item in raw:
                        # Binance format: [open_time, open, high, low, close, volume, close_time, ...]
                        open_time_ms = int(item[0])
                        close_time_ms = int(item[6])
                        dt_iso = datetime.fromtimestamp(open_time_ms / 1000.0, tz=timezone.utc).isoformat()
                        candles.append({
                            "timestamp": dt_iso,
                            "open": float(item[1]),
                            "high": float(item[2]),
                            "low": float(item[3]),
                            "close": float(item[4]),
                            "volume": float(item[5]),
                            "open_time_ms": open_time_ms,
                            "close_time_ms": close_time_ms
                        })
                    return candles
            except Exception as e:
                logger.debug(f"Binance candles failed on {base}: {e}")
        return []

    def _fetch_coinbase_candles(self, timeframe: str, limit: int = 60) -> List[Dict[str, Any]]:
        granularity = self.TIMEFRAME_MAP_COINBASE.get(timeframe, 900)
        try:
            url = f"{self.COINBASE_URL}/candles"
            params = {"granularity": granularity}
            resp = self.session.get(url, params=params, timeout=5)
            if resp.status_code == 200:
                raw = resp.json()
                candles = []
                for item in raw:
                    # Coinbase format: [time, low, high, open, close, volume]
                    time_sec = int(item[0])
                    dt_iso = datetime.fromtimestamp(time_sec, tz=timezone.utc).isoformat()
                    candles.append({
                        "timestamp": dt_iso,
                        "low": float(item[1]),
                        "high": float(item[2]),
                        "open": float(item[3]),
                        "close": float(item[4]),
                        "volume": float(item[5]),
                        "open_time_ms": time_sec * 1000,
                        "close_time_ms": (time_sec + granularity) * 1000
                    })
                candles.sort(key=lambda x: x["timestamp"])
                return candles[-limit:]
        except Exception as e:
            logger.debug(f"Coinbase candles fetch failed: {e}")
        return []
