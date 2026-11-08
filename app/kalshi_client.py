"""Kalshi Trade API v2 Client for discovering and inspecting BTC prediction markets."""

from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, List, Optional
import requests

from app.config import Settings

logger = logging.getLogger("KalshiClient")


class KalshiClient:
    """Client for Kalshi Public Trade API v2."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.kalshi_api_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "BTC-Scalping-AI/1.0"
        })

    def _request_with_retry(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
        backoff_sec: float = 1.0
    ) -> Optional[Dict[str, Any]]:
        """Makes an HTTP request with exponential backoff and error handling."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        for attempt in range(1, max_retries + 1):
            try:
                resp = self.session.request(method=method, url=url, params=params, timeout=8)
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 429:
                    wait_time = backoff_sec * (2 ** (attempt - 1))
                    logger.warning(f"Rate limited by Kalshi API (429). Retrying in {wait_time:.1f}s...")
                    time.sleep(wait_time)
                elif resp.status_code == 404:
                    logger.debug(f"Kalshi resource not found (404): {endpoint}")
                    return None
                else:
                    logger.warning(f"Kalshi API responded with status {resp.status_code}: {resp.text[:150]}")
                    time.sleep(backoff_sec)
            except requests.RequestException as e:
                logger.warning(f"Network error on Kalshi API ({endpoint}), attempt {attempt}/{max_retries}: {e}")
                time.sleep(backoff_sec)

        logger.error(f"Failed to fetch {endpoint} after {max_retries} attempts.")
        return None

    def get_series(self, series_ticker: str) -> Optional[Dict[str, Any]]:
        """Fetches series details from Kalshi."""
        data = self._request_with_retry("GET", f"/series/{series_ticker}")
        if data and "series" in data:
            return data["series"]
        return None

    def get_markets_for_series(self, series_ticker: str) -> List[Dict[str, Any]]:
        """Fetches raw markets list for a series ticker."""
        params = {"series_ticker": series_ticker, "limit": 100}
        data = self._request_with_retry("GET", "/markets", params=params)
        if data and "markets" in data:
            return data["markets"]
        return []

    def get_market_orderbook(self, ticker: str, depth: int = 5) -> Optional[Dict[str, Any]]:
        """Fetches orderbook for a specific market ticker."""
        params = {"depth": depth}
        data = self._request_with_retry("GET", f"/markets/{ticker}/orderbook", params=params)
        if data and "orderbook" in data:
            return data["orderbook"]
        return None

    def find_active_btc_market(self) -> Tuple[Optional[Dict[str, Any]], str]:
        """Discovers the best active BTC market by checking the target series and fallbacks.

        Returns:
            Tuple of (market_dict, series_ticker_used)
        """
        all_series = [self.settings.kalshi_target_series] + self.settings.kalshi_fallback_series

        for series in all_series:
            series = series.strip()
            if not series:
                continue

            raw_markets = self.get_markets_for_series(series)
            if not raw_markets:
                logger.debug(f"No markets found under series {series}")
                continue

            # Filter for active or open markets
            # Kalshi API statuses: 'active', 'open', 'initialized'
            active_markets = [
                m for m in raw_markets
                if m.get("status") in ("active", "open")
            ]

            if not active_markets:
                # Fallback to initialized if it opens soon
                active_markets = [m for m in raw_markets if m.get("status") == "initialized"]

            if active_markets:
                # Parse and select the market with the closest upcoming expiration/close_time
                parsed_list = []
                for m in active_markets:
                    parsed = self._parse_market(m, series)
                    if parsed:
                        parsed_list.append(parsed)

                if parsed_list:
                    # Sort by seconds remaining ascending (closest to maturity first, but > 0 if active)
                    # Filter for markets that haven't closed yet
                    open_now = [p for p in parsed_list if p["seconds_remaining"] > 0]
                    if open_now:
                        open_now.sort(key=lambda x: x["seconds_remaining"])
                        selected = open_now[0]
                        logger.info(f"Selected active Kalshi market: {selected['ticker']} ({selected['title']}) under series {series}")
                        return selected, series
                    else:
                        # Return the earliest upcoming initialized one
                        parsed_list.sort(key=lambda x: abs(x["seconds_remaining"]))
                        return parsed_list[0], series

        logger.warning(f"No active BTC markets found across series: {all_series}")
        return None, ""

    def _parse_market(self, raw: Dict[str, Any], series_ticker: str) -> Optional[Dict[str, Any]]:
        """Normalizes Kalshi raw market data into our standard contract representation."""
        try:
            ticker = raw.get("ticker", "")
            title = raw.get("title", "")
            status = raw.get("status", "unknown")

            # Parse pricing in cents (0 - 100)
            yes_bid = self._dollars_to_cents(raw.get("yes_bid_dollars"))
            yes_ask = self._dollars_to_cents(raw.get("yes_ask_dollars"))
            no_bid = self._dollars_to_cents(raw.get("no_bid_dollars"))
            no_ask = self._dollars_to_cents(raw.get("no_ask_dollars"))
            last_price = self._dollars_to_cents(raw.get("last_price_dollars"))

            # Derive synthetic prices if missing
            if yes_ask is None and no_bid is not None:
                yes_ask = 100 - no_bid
            if yes_bid is None and no_ask is not None:
                yes_bid = 100 - no_ask
            if no_ask is None and yes_bid is not None:
                no_ask = 100 - yes_bid
            if no_bid is None and yes_ask is not None:
                no_bid = 100 - yes_ask

            # Strike price
            floor_strike = raw.get("floor_strike")
            cap_strike = raw.get("cap_strike")
            strike_price = floor_strike if floor_strike is not None else cap_strike

            # Close / expiration time
            close_time_str = raw.get("close_time") or raw.get("expected_expiration_time") or raw.get("expiration_time")
            seconds_remaining = 0
            time_remaining_str = "Desconocido"

            if close_time_str:
                try:
                    # Clean ISO format
                    dt_str = close_time_str.replace("Z", "+00:00")
                    exp_dt = datetime.fromisoformat(dt_str)
                    now_dt = datetime.now(timezone.utc)
                    diff = (exp_dt - now_dt).total_seconds()
                    seconds_remaining = max(0, int(diff))
                    mins = seconds_remaining // 60
                    secs = seconds_remaining % 60
                    time_remaining_str = f"{mins:02d}:{secs:02d}"
                except Exception as e:
                    logger.debug(f"Could not parse expiration time {close_time_str}: {e}")

            rules = raw.get("rules_primary", "")
            if raw.get("rules_secondary"):
                rules += " | " + raw.get("rules_secondary")

            subtitle = raw.get("yes_sub_title", "")
            target_str = subtitle.replace("Target Price:", "").replace("Target price:", "").strip()

            return {
                "ticker": ticker,
                "series_ticker": series_ticker,
                "title": title,
                "status": status,
                "yes_bid": yes_bid,
                "yes_ask": yes_ask,
                "no_bid": no_bid,
                "no_ask": no_ask,
                "last_price": last_price,
                "strike_price": float(strike_price) if strike_price is not None else None,
                "to_beat_str": target_str if target_str else (f"${float(strike_price):,.2f}" if strike_price else "TBD"),
                "close_time": close_time_str,
                "seconds_remaining": seconds_remaining,
                "time_remaining_str": time_remaining_str,
                "settlement_rules": rules,
                "volume": float(raw.get("volume_fp", 0.0) or 0.0),
                "open_interest": float(raw.get("open_interest_fp", 0.0) or 0.0),
                "raw": raw
            }
        except Exception as e:
            logger.error(f"Error parsing Kalshi market: {e}")
            return None

    @staticmethod
    def _dollars_to_cents(val: Any) -> Optional[float]:
        if val is None or val == "":
            return None
        try:
            return round(float(val) * 100.0, 2)
        except (ValueError, TypeError):
            return None

