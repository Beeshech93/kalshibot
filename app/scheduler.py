"""Autonomous Scheduler for BTC SCALPING AI.
Executes the market analysis cycle every 15 minutes, discovers Kalshi contracts,
generates signals, and broadcasts reports.
"""

from datetime import datetime, timezone
import logging
import threading
import time
from typing import Optional

from app.config import Settings
from app.database import Database
from app.kalshi_client import KalshiClient
from app.market_data import MarketDataManager
from app.performance import PerformanceTracker
from app.signal_engine import SignalEngine
from app.technical_analysis import TechnicalAnalysis
from app.telegram_bot import TelegramBot

logger = logging.getLogger("Scheduler")


class AnalysisScheduler:
    """Manages periodic execution of the 15-minute BTC scalping analysis pipeline."""

    def __init__(
        self,
        settings: Settings,
        db: Database,
        market_data: MarketDataManager,
        kalshi: KalshiClient,
        signal_engine: SignalEngine,
        telegram_bot: TelegramBot
    ):
        self.settings = settings
        self.db = db
        self.market_data = market_data
        self.kalshi = kalshi
        self.signal_engine = signal_engine
        self.telegram_bot = telegram_bot
        self.performance_tracker = PerformanceTracker(db)

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_run_timestamp: Optional[datetime] = None

    def start(self) -> None:
        """Starts the scheduler thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="SchedulerThread")
        self._thread.start()
        logger.info(f"Scheduler started with {self.settings.analysis_interval_minutes}m interval.")

    def stop(self) -> None:
        """Stops the scheduler thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        logger.info("Scheduler stopped.")

    def execute_cycle(self, force_broadcast: bool = False) -> None:
        """Executes a single end-to-end analysis and signal generation cycle."""
        logger.info("--- Starting BTC Scalping Analysis Cycle ---")
        try:
            # 1. Fetch current live BTC price
            btc_price = self.market_data.get_current_btc_price()
            if not btc_price:
                logger.error("Could not obtain BTC spot price. Aborting cycle.")
                self.db.log_event("ERROR", "Scheduler", "Fallo al obtener precio spot BTC.")
                return

            logger.info(f"Spot BTC Price: ${btc_price:,.2f}")

            # 2. Fetch multi-timeframe closed candles
            mtf_candles = self.market_data.get_multi_timeframe_candles(limit=60)

            # 3. Perform Technical Analysis
            mtf_analysis = TechnicalAnalysis.analyze_multi_timeframe(mtf_candles)
            ind_15m = mtf_analysis.get("15m")
            if not ind_15m:
                logger.warning("Technical analysis incomplete due to insufficient candle history.")
                self.db.log_event("WARNING", "Scheduler", "Velas insuficientes para cálculo de indicadores.")
                return

            # 4. Query Kalshi Market
            kalshi_market, series_used = self.kalshi.find_active_btc_market()
            if kalshi_market:
                self.db.upsert_market(kalshi_market)
                logger.info(f"Active Kalshi Contract: {kalshi_market['ticker']} | Strike: {kalshi_market.get('strike_price')} | Left: {kalshi_market.get('time_remaining_str')}")
            else:
                logger.warning(f"No active Kalshi contract found under {self.settings.kalshi_target_series}. Checking fallbacks.")
                self.db.log_event("WARNING", "Scheduler", f"Sin mercado activo en Kalshi serie {self.settings.kalshi_target_series}.")

            # 5. Generate Signal
            decision = self.signal_engine.evaluate(
                mtf_analysis=mtf_analysis,
                kalshi_market=kalshi_market,
                current_btc_price=btc_price
            )

            # 6. Check duplicate signal prevention
            mkt_ticker = decision.market_ticker
            is_duplicate = False
            if mkt_ticker and mkt_ticker != "N/A":
                is_duplicate = self.db.has_recent_signal(mkt_ticker, within_minutes=self.settings.analysis_interval_minutes - 1)

            # 7. Store signal in Database
            signal_id = None
            if not is_duplicate:
                signal_id = self.db.insert_signal(
                    market_ticker=decision.market_ticker,
                    btc_price=decision.btc_price,
                    contract_price=decision.contract_price,
                    signal_type=decision.signal_type,
                    indicators=decision.indicators,
                    confidence_score=decision.confidence_score,
                    reference_price=decision.reference_price,
                    technical_justification=decision.technical_justification
                )
            else:
                logger.info(f"Duplicate signal suppressed for {mkt_ticker} (already recorded within interval).")

            # 8. Evaluate past signals
            self.performance_tracker.evaluate_settled_signals(btc_price)

            # 9. Send Telegram Broadcast
            if not is_duplicate or force_broadcast:
                self.telegram_bot.broadcast_signal_if_new(
                    signal_decision=decision,
                    kalshi_market=kalshi_market,
                    indicators=ind_15m.to_dict(),
                    force=force_broadcast
                )

            self._last_run_timestamp = datetime.now(timezone.utc)
            self.db.log_event("INFO", "Scheduler", f"Ciclo completado. Señal: {decision.signal_type} ({decision.confidence_score:.1f}%)")
            logger.info(f"--- Analysis Cycle Complete: Signal={decision.signal_type} ({decision.confidence_score:.1f}%) ---")

        except Exception as e:
            logger.exception(f"Unexpected error during analysis cycle: {e}")
            self.db.log_event("ERROR", "Scheduler", f"Error en ciclo: {str(e)}")

    def _run_loop(self) -> None:
        """Loop running every analysis_interval_minutes."""
        # Run first cycle immediately
        self.execute_cycle(force_broadcast=True)

        interval_sec = self.settings.analysis_interval_minutes * 60
        while self._running:
            # Sleep in small slices to allow responsive stop
            for _ in range(interval_sec):
                if not self._running:
                    break
                time.sleep(1)

            if self._running:
                self.execute_cycle(force_broadcast=False)
