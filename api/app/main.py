"""Main application entry point for BTC SCALPING AI."""

import logging
import os
from pathlib import Path
import signal
import sys
import time

from app.config import settings
from app.database import Database
from app.kalshi_client import KalshiClient
from app.market_data import MarketDataManager
from app.scheduler import AnalysisScheduler
from app.signal_engine import SignalEngine
from app.telegram_bot import TelegramBot


def setup_logging():
    """Configures structured logging to console and file without leaking secrets."""
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = settings.logs_dir / "btc_scalping.log"

    log_format = "%(asctime)s [%(levelname)s] (%(name)s) %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    level = getattr(logging, settings.log_level, logging.INFO)

    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(log_file), encoding="utf-8")
    ]

    logging.basicConfig(level=level, format=log_format, datefmt=date_format, handlers=handlers)


def main():
    """Initializes and runs the BTC SCALPING AI system."""
    setup_logging()
    logger = logging.getLogger("Main")

    logger.info("==================================================")
    logger.info("             BTC SCALPING AI v1.0.0               ")
    logger.info("   Autonomous Bitcoin & Kalshi Prediction Agent   ")
    logger.info("==================================================")
    logger.info(f"Execution Mode: {settings.mode}")
    logger.info(f"Target Kalshi Series: {settings.kalshi_target_series}")
    logger.info(f"Analysis Interval: {settings.analysis_interval_minutes} minutes")
    logger.info(f"Min Confidence Threshold: {settings.min_confidence_score}%")
    logger.info(f"Database Path: {settings.database_path}")

    # 1. Initialize Database
    db = Database(settings.database_path)

    # 2. Initialize Market Data Provider
    market_data = MarketDataManager(db=db)

    # 3. Initialize Kalshi Client
    kalshi = KalshiClient(settings)

    # 4. Initialize Signal Engine
    signal_engine = SignalEngine(min_confidence=float(settings.min_confidence_score))

    # 5. Initialize Telegram Bot
    telegram_bot = TelegramBot(
        settings=settings,
        db=db,
        market_data=market_data,
        kalshi=kalshi,
        signal_engine=signal_engine
    )

    # 6. Initialize Scheduler
    scheduler = AnalysisScheduler(
        settings=settings,
        db=db,
        market_data=market_data,
        kalshi=kalshi,
        signal_engine=signal_engine,
        telegram_bot=telegram_bot
    )

    # Graceful shutdown handler
    def handle_exit_signal(sig, frame):
        logger.info(f"Received shutdown signal ({sig}). Stopping bot gracefully...")
        scheduler.stop()
        telegram_bot.stop_polling()
        logger.info("BTC SCALPING AI stopped.")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_exit_signal)
    signal.signal(signal.SIGTERM, handle_exit_signal)

    # Start Telegram polling if configured
    if telegram_bot.is_configured:
        telegram_bot.start_polling()
    else:
        logger.info("Telegram Bot token not provided in .env; notifications disabled.")

    # Start the autonomous analysis scheduler
    scheduler.start()

    logger.info("System fully operational. Running market analysis loop...")

    # Keep main process alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        handle_exit_signal(signal.SIGINT, None)


if __name__ == "__main__":
    main()

