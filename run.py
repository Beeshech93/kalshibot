#!/usr/bin/env python3
"""Runner script for BTC SCALPING AI.
Supports running the autonomous bot, the web dashboard, or both simultaneously.
"""

import argparse
import logging
import signal
import sys
import threading
import time

from app.config import settings
from app.database import Database
from app.kalshi_client import KalshiClient
from app.market_data import MarketDataManager
from app.scheduler import AnalysisScheduler
from app.signal_engine import SignalEngine
from app.telegram_bot import TelegramBot
from dashboard.app import app as flask_app


def run_bot_service():
    """Starts the bot analysis engine and Telegram polling."""
    db = Database(settings.database_path)
    market_data = MarketDataManager(db=db)
    kalshi = KalshiClient(settings)
    signal_engine = SignalEngine(min_confidence=float(settings.min_confidence_score))
    telegram_bot = TelegramBot(settings, db, market_data, kalshi, signal_engine)
    scheduler = AnalysisScheduler(settings, db, market_data, kalshi, signal_engine, telegram_bot)

    if telegram_bot.is_configured:
        telegram_bot.start_polling()

    scheduler.start()
    return scheduler, telegram_bot


def run_single_cycle():
    """Executes a single end-to-end analysis cycle and prints output."""
    print("=" * 60)
    print("      BTC SCALPING AI — Ejecución de Ciclo Único")
    print("=" * 60)
    db = Database(settings.database_path)
    market_data = MarketDataManager(db=db)
    kalshi = KalshiClient(settings)
    signal_engine = SignalEngine(min_confidence=float(settings.min_confidence_score))
    telegram_bot = TelegramBot(settings, db, market_data, kalshi, signal_engine)
    scheduler = AnalysisScheduler(settings, db, market_data, kalshi, signal_engine, telegram_bot)

    scheduler.execute_cycle(force_broadcast=True)

    sig = db.get_latest_signal()
    if sig:
        print("\n[RESULTADO DEL ANÁLISIS]")
        print(f"• Mercado: {sig['market_ticker']}")
        print(f"• Spot BTC: ${sig['btc_price']:,.2f}")
        print(f"• Señal Emitida: {sig['signal_type']}")
        print(f"• Confianza del Modelo: {sig['confidence_score']:.1f}%")
        print(f"• Justificación Técnica: {sig.get('technical_justification')}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="BTC SCALPING AI — Runner")
    parser.add_argument("--bot", action="store_true", help="Ejecutar solo el bot de análisis y Telegram")
    parser.add_argument("--dashboard", action="store_true", help="Ejecutar solo el dashboard web")
    parser.add_argument("--once", action="store_true", help="Ejecutar un solo ciclo de análisis y salir")
    parser.add_argument("--host", default=settings.dashboard_host, help="Host para el dashboard")
    parser.add_argument("--port", type=int, default=settings.dashboard_port, help="Puerto para el dashboard")

    args = parser.parse_args()

    # Logging setup
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] (%(name)s) %(message)s"
    )

    if args.once:
        run_single_cycle()
        return

    if args.bot and not args.dashboard:
        # Run only bot
        scheduler, bot = run_bot_service()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            scheduler.stop()
            bot.stop_polling()
            print("\nBot detenido.")
        return

    if args.dashboard and not args.bot:
        # Run only dashboard
        print(f"Iniciando Dashboard Web en http://{args.host}:{args.port}")
        flask_app.run(host=args.host, port=args.port, debug=settings.dashboard_debug)
        return

    # Default: Run BOTH in parallel
    print("==================================================")
    print("             BTC SCALPING AI v1.0.0               ")
    print("   Bot de Señales + Dashboard Web Concurrente     ")
    print("==================================================")
    print(f"• Dashboard: http://{args.host}:{args.port}")
    print(f"• Intervalo de análisis: {settings.analysis_interval_minutes} minutos")
    print(f"• Presiona Ctrl+C para detener el sistema.")
    print("==================================================")

    scheduler, bot = run_bot_service()

    # Run Flask in separate thread or main thread
    def run_flask():
        flask_app.run(host=args.host, port=args.port, debug=False, use_reloader=False)

    flask_thread = threading.Thread(target=run_flask, daemon=True, name="FlaskThread")
    flask_thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nDeteniendo BTC SCALPING AI...")
        scheduler.stop()
        bot.stop_polling()
        print("Sistema finalizado limpiamente.")


if __name__ == "__main__":
    main()

