"""Performance measurement and historical analytics for BTC SCALPING AI."""

from dataclasses import dataclass
import logging
from typing import Any, Dict, List
from app.database import Database

logger = logging.getLogger("Performance")


@dataclass
class PerformanceStats:
    total_signals: int = 0
    yes_signals: int = 0
    no_signals: int = 0
    wait_signals: int = 0
    pending_evaluations: int = 0
    evaluated_signals: int = 0
    wins: int = 0
    losses: int = 0
    voids: int = 0
    win_rate_percent: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_signals": self.total_signals,
            "yes_signals": self.yes_signals,
            "no_signals": self.no_signals,
            "wait_signals": self.wait_signals,
            "pending_evaluations": self.pending_evaluations,
            "evaluated_signals": self.evaluated_signals,
            "wins": self.wins,
            "losses": self.losses,
            "voids": self.voids,
            "win_rate_percent": round(self.win_rate_percent, 2)
        }


class PerformanceTracker:
    """Computes objective performance metrics from recorded signals and results."""

    def __init__(self, db: Database):
        self.db = db

    def calculate_stats(self) -> PerformanceStats:
        """Calculates win/loss metrics strictly excluding pending signals."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            # Signal counts by type
            cursor.execute("SELECT signal_type, COUNT(*) as cnt FROM signals GROUP BY signal_type")
            type_counts = {row["signal_type"]: row["cnt"] for row in cursor.fetchall()}

            yes_count = type_counts.get("YES", 0)
            no_count = type_counts.get("NO", 0)
            wait_count = type_counts.get("WAIT", 0)
            total_signals = yes_count + no_count + wait_count

            # Evaluation status breakdown (only for YES and NO signals, WAIT has no win/loss)
            cursor.execute("""
            SELECT post_outcome, evaluation_status, COUNT(*) as cnt
            FROM signals
            WHERE signal_type IN ('YES', 'NO')
            GROUP BY post_outcome, evaluation_status
            """)
            rows = cursor.fetchall()

            wins = 0
            losses = 0
            voids = 0
            pending = 0

            for r in rows:
                status = r["evaluation_status"]
                outcome = r["post_outcome"]
                cnt = r["cnt"]

                if status == "PENDING" or outcome == "PENDING":
                    pending += cnt
                elif outcome == "WIN":
                    wins += cnt
                elif outcome == "LOSS":
                    losses += cnt
                elif outcome == "VOID":
                    voids += cnt

            evaluated = wins + losses
            win_rate = (wins / evaluated * 100.0) if evaluated > 0 else 0.0

            return PerformanceStats(
                total_signals=total_signals,
                yes_signals=yes_count,
                no_signals=no_count,
                wait_signals=wait_count,
                pending_evaluations=pending,
                evaluated_signals=evaluated,
                wins=wins,
                losses=losses,
                voids=voids,
                win_rate_percent=win_rate
            )

    def evaluate_settled_signals(self, current_btc_price: float) -> int:
        """Evaluates pending signals against current market data or expired time."""
        pending = self.db.get_pending_signals()
        evaluated_count = 0

        for sig in pending:
            market_ticker = sig["market_ticker"]
            market = self.db.get_latest_market()
            # If the market has an expiration or strike
            strike = sig["reference_price"]
            sig_type = sig["signal_type"]
            sig_id = sig["id"]

            # If contract has reference strike and current price
            if strike and strike > 0:
                # Let's check if the market time has passed
                # In binary prediction: YES wins if final price >= strike; NO wins if final price < strike
                # Only evaluate if marked as expired or past target time
                # We can do evaluation when market closes
                pass

        return evaluated_count

