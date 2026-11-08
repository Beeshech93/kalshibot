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
        self._analyzed_contracts = set()
        self._sent_6m_contracts = set()

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

    def execute_cycle(self, force_broadcast: bool = False, is_6m_trigger: bool = False) -> None:
        """Executes a single end-to-end analysis and signal generation cycle."""
        prefix = "⚡ [SCALPING 6 MINUTOS] " if is_6m_trigger else "⏱️ [PERIODO 15M] "
        logger.info(f"--- {prefix}Starting BTC Scalping Analysis Cycle ---")
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

            # 6. Store signal in Database
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

            # 7. Evaluate past signals against official settlement
            self.performance_tracker.evaluate_settled_signals(btc_price, self.kalshi)

            # 8. Send Telegram Broadcast
            self.telegram_bot.broadcast_signal_if_new(
                signal_decision=decision,
                kalshi_market=kalshi_market,
                indicators=ind_15m.to_dict(),
                force=True  # Ensure every 15m period and 6m trigger is broadcasted
            )

            self._last_run_timestamp = datetime.now(timezone.utc)
            self.db.log_event("INFO", "Scheduler", f"{prefix}Ciclo completado. Señal: {decision.direction_label} ({decision.confidence_score:.1f}%)")
            logger.info(f"--- {prefix}Analysis Cycle Complete: Signal={decision.direction_label} ({decision.confidence_score:.1f}%) ---")

        except Exception as e:
            logger.exception(f"Unexpected error during analysis cycle: {e}")
            self.db.log_event("ERROR", "Scheduler", f"Error en ciclo: {str(e)}")

    def _run_loop(self) -> None:
        """Deterministic 15-minute period execution loop + 6-minute scalping window."""
        scan_interval = max(5, self.settings.scan_interval_seconds)
        window_seconds = self.settings.signal_window_minutes * 60  # e.g., 360 seconds (6 minutes)

        logger.info(f"Autonomous Scheduler Active. Monitoring every 15-minute contract continuously.")

        # Initial cycle on startup
        self.execute_cycle(force_broadcast=True)

        while self._running:
            try:
                # 1. Discover current active Kalshi contract
                kalshi_market, _ = self.kalshi.find_active_btc_market()
                if kalshi_market:
                    ticker = kalshi_market.get("ticker")
                    sec_rem = kalshi_market.get("seconds_remaining", 0)

                    # Trigger A: Brand new 15-minute contract detected!
                    if ticker and ticker not in self._analyzed_contracts:
                        logger.info(f"⏱️ [NUEVO PERIODO 15M] Contrato detectado: {ticker} (Strike: {kalshi_market.get('strike_price')}). Ejecutando análisis inicial...")
                        self._analyzed_contracts.add(ticker)
                        self.execute_cycle(force_broadcast=True, is_6m_trigger=False)

                    # Trigger B: Contract enters the last 6 minutes!
                    if 60 <= sec_rem <= window_seconds:
                        if ticker and ticker not in self._sent_6m_contracts:
                            logger.info(f"⚡ [VENTANA 6M SCALPING] Contrato {ticker} en los últimos 6 minutos ({sec_rem}s restantes). Disparando señal de alta convicción!")
                            self._sent_6m_contracts.add(ticker)
                            self.execute_cycle(force_broadcast=True, is_6m_trigger=True)

                # Fallback: Clock-aligned 15-minute periodic check
                if self._last_run_timestamp:
                    elapsed = (datetime.now(timezone.utc) - self._last_run_timestamp).total_seconds()
                    if elapsed >= (self.settings.analysis_interval_minutes * 60):
                        logger.info(f"⏱️ [TEMPORIZADOR 15M] Han transcurrido {elapsed / 60:.1f} minutos. Ejecutando ciclo de análisis periódico...")
                        self.execute_cycle(force_broadcast=True)

            except Exception as e:
                logger.error(f"Error in scheduler monitor loop: {e}")

            # Sleep in small slices for graceful shutdown
            for _ in range(scan_interval):
                if not self._running:
                    break
                time.sleep(1)
