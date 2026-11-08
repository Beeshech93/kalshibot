"""Database module for BTC SCALPING AI using SQLite."""

from datetime import datetime, timezone
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("Database")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    """Manages SQLite storage for markets, signals, prices, logs, and performance."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()

    def _get_connection(self) -> sqlite3.Connection:
        """Creates a connection with row factory enabled."""
        conn = sqlite3.connect(str(self.db_path), timeout=20.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self) -> None:
        """Initializes all required tables if they do not exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 1. markets
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS markets (
                ticker TEXT PRIMARY KEY,
                series_ticker TEXT NOT NULL,
                title TEXT,
                status TEXT,
                yes_bid REAL,
                yes_ask REAL,
                no_bid REAL,
                no_ask REAL,
                last_price REAL,
                strike_price REAL,
                expiration_time TEXT,
                settlement_rules TEXT,
                updated_at TEXT NOT NULL
            );
            """)

            # 2. signals
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                market_ticker TEXT NOT NULL,
                btc_price REAL NOT NULL,
                contract_price REAL,
                signal_type TEXT NOT NULL,
                indicators TEXT NOT NULL,
                confidence_score REAL NOT NULL,
                reference_price REAL,
                post_outcome TEXT DEFAULT 'PENDING',
                evaluation_status TEXT DEFAULT 'PENDING',
                technical_justification TEXT,
                created_at TEXT NOT NULL
            );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_signals_market ON signals(market_ticker);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_signals_eval ON signals(evaluation_status);")

            # 3. price_history
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                UNIQUE(symbol, timeframe, timestamp)
            );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_hist ON price_history(symbol, timeframe, timestamp);")

            # 4. signal_results
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS signal_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id INTEGER NOT NULL,
                evaluated_at TEXT NOT NULL,
                final_btc_price REAL,
                kalshi_result TEXT,
                outcome TEXT NOT NULL,
                notes TEXT,
                FOREIGN KEY (signal_id) REFERENCES signals(id)
            );
            """)

            # 5. bot_logs
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS bot_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                level TEXT NOT NULL,
                module TEXT NOT NULL,
                message TEXT NOT NULL
            );
            """)

            # 6. settings
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """)

            conn.commit()
            logger.debug(f"Database initialized at {self.db_path}")

    # --- Market Operations ---

    def upsert_market(self, market_data: Dict[str, Any]) -> None:
        """Inserts or updates market data from Kalshi."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO markets (
                ticker, series_ticker, title, status,
                yes_bid, yes_ask, no_bid, no_ask, last_price,
                strike_price, expiration_time, settlement_rules, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                series_ticker = excluded.series_ticker,
                title = excluded.title,
                status = excluded.status,
                yes_bid = excluded.yes_bid,
                yes_ask = excluded.yes_ask,
                no_bid = excluded.no_bid,
                no_ask = excluded.no_ask,
                last_price = excluded.last_price,
                strike_price = excluded.strike_price,
                expiration_time = excluded.expiration_time,
                settlement_rules = excluded.settlement_rules,
                updated_at = excluded.updated_at;
            """, (
                market_data.get("ticker"),
                market_data.get("series_ticker", ""),
                market_data.get("title", ""),
                market_data.get("status", "open"),
                market_data.get("yes_bid"),
                market_data.get("yes_ask"),
                market_data.get("no_bid"),
                market_data.get("no_ask"),
                market_data.get("last_price"),
                market_data.get("strike_price"),
                market_data.get("expiration_time"),
                market_data.get("settlement_rules", ""),
                _utc_now_iso()
            ))
            conn.commit()

    def get_latest_market(self, series_ticker: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Gets the most relevant active market."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM markets WHERE status = 'open'"
            params: List[Any] = []
            if series_ticker:
                query += " AND series_ticker = ?"
                params.append(series_ticker)
            query += " ORDER BY expiration_time ASC LIMIT 1"
            cursor.execute(query, params)
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_active_markets(self) -> List[Dict[str, Any]]:
        """Returns all open markets ordered by expiration."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM markets WHERE status = 'open' ORDER BY expiration_time ASC")
            return [dict(row) for row in cursor.fetchall()]

    # --- Signal Operations ---

    def insert_signal(
        self,
        market_ticker: str,
        btc_price: float,
        contract_price: Optional[float],
        signal_type: str,
        indicators: Dict[str, Any],
        confidence_score: float,
        reference_price: Optional[float],
        technical_justification: str
    ) -> int:
        """Inserts a generated signal into the database."""
        now = _utc_now_iso()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO signals (
                timestamp, market_ticker, btc_price, contract_price,
                signal_type, indicators, confidence_score, reference_price,
                post_outcome, evaluation_status, technical_justification, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', 'PENDING', ?, ?)
            """, (
                now,
                market_ticker,
                btc_price,
                contract_price,
                signal_type,
                json.dumps(indicators),
                confidence_score,
                reference_price,
                technical_justification,
                now
            ))
            conn.commit()
            signal_id = cursor.lastrowid
            logger.info(f"Recorded signal #{signal_id}: {signal_type} on {market_ticker} (Confidence: {confidence_score:.1f})")
            return signal_id

    def has_recent_signal(self, market_ticker: str, within_minutes: int = 14) -> bool:
        """Checks if a signal has already been generated recently for this market to avoid duplicates."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT id, timestamp FROM signals
            WHERE market_ticker = ?
            ORDER BY id DESC LIMIT 1
            """, (market_ticker,))
            row = cursor.fetchone()
            if not row:
                return False

            try:
                sig_time = datetime.fromisoformat(row["timestamp"])
                now = datetime.now(timezone.utc)
                if sig_time.tzinfo is None:
                    sig_time = sig_time.replace(tzinfo=timezone.utc)
                diff = (now - sig_time).total_seconds() / 60.0
                return diff < within_minutes
            except Exception:
                return False

    def get_latest_signal(self) -> Optional[Dict[str, Any]]:
        """Gets the most recently generated signal."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM signals ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            if not row:
                return None
            res = dict(row)
            try:
                res["indicators"] = json.loads(res["indicators"])
            except Exception:
                pass
            return res

    def get_recent_signals(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns recent signals list."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM signals ORDER BY id DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            results = []
            for row in rows:
                item = dict(row)
                try:
                    item["indicators"] = json.loads(item["indicators"])
                except Exception:
                    pass
                results.append(item)
            return results

    def get_pending_signals(self) -> List[Dict[str, Any]]:
        """Fetches signals that are pending evaluation."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM signals WHERE evaluation_status = 'PENDING' AND signal_type IN ('YES', 'NO')")
            return [dict(r) for r in cursor.fetchall()]

    def update_signal_outcome(
        self,
        signal_id: int,
        outcome: str,
        final_btc_price: Optional[float] = None,
        kalshi_result: Optional[str] = None,
        notes: str = ""
    ) -> None:
        """Updates signal evaluation outcome (WIN / LOSS / VOID)."""
        now = _utc_now_iso()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE signals
            SET post_outcome = ?, evaluation_status = 'EVALUATED'
            WHERE id = ?
            """, (outcome, signal_id))

            cursor.execute("""
            INSERT INTO signal_results (signal_id, evaluated_at, final_btc_price, kalshi_result, outcome, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (signal_id, now, final_btc_price, kalshi_result, outcome, notes))

            conn.commit()
            logger.info(f"Signal #{signal_id} evaluated: {outcome} ({notes})")

    # --- Price History Operations ---

    def insert_candles(self, symbol: str, timeframe: str, candles: List[Dict[str, Any]]) -> None:
        """Inserts multiple OHLCV candles."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for c in candles:
                cursor.execute("""
                INSERT OR REPLACE INTO price_history (timestamp, symbol, timeframe, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    c["timestamp"],
                    symbol,
                    timeframe,
                    float(c["open"]),
                    float(c["high"]),
                    float(c["low"]),
                    float(c["close"]),
                    float(c["volume"])
                ))
            conn.commit()

    def get_candles(self, symbol: str, timeframe: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieves recent candles sorted by timestamp ascending."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT * FROM (
                SELECT timestamp, open, high, low, close, volume
                FROM price_history
                WHERE symbol = ? AND timeframe = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ) ORDER BY timestamp ASC
            """, (symbol, timeframe, limit))
            return [dict(r) for r in cursor.fetchall()]

    # --- Logs & Settings ---

    def log_event(self, level: str, module: str, message: str) -> None:
        """Stores a bot log event."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO bot_logs (timestamp, level, module, message)
            VALUES (?, ?, ?, ?)
            """, (_utc_now_iso(), level, module, message))
            conn.commit()

    def get_recent_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieves recent bot logs."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM bot_logs ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(r) for r in cursor.fetchall()]

    def set_setting(self, key: str, value: str) -> None:
        """Sets or updates a setting."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """, (key, value, _utc_now_iso()))
            conn.commit()

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Gets a setting value."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else default
