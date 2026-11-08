"""Web Dashboard for BTC SCALPING AI.
Provides real-time dark financial UI, charts, signals, and performance metrics.
"""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from flask import Flask, jsonify, render_template, request

from app.config import settings
from app.database import Database
from app.kalshi_client import KalshiClient
from app.market_data import MarketDataManager
from app.performance import PerformanceTracker
from app.signal_engine import SignalEngine
from app.technical_analysis import TechnicalAnalysis

logger = logging.getLogger("Dashboard")

app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / "templates"),
    static_folder=str(Path(__file__).parent / "static")
)

# Shared instances
db = Database(settings.database_path)
market_data = MarketDataManager(db=db)
kalshi = KalshiClient(settings)
signal_engine = SignalEngine(min_confidence=float(settings.min_confidence_score))
perf_tracker = PerformanceTracker(db)


@app.route("/")
def index():
    """Renders the main dashboard page."""
    return render_template("index.html")


@app.route("/api/overview")
def api_overview():
    """Returns aggregated state for quick UI refresh."""
    btc_price = market_data.get_current_btc_price()
    latest_sig = db.get_latest_signal()
    active_mkt, series_used = kalshi.find_active_btc_market()
    stats = perf_tracker.calculate_stats().to_dict()

    return jsonify({
        "status": "ONLINE",
        "mode": settings.mode,
        "btc_price": btc_price,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "latest_signal": latest_sig,
        "active_market": active_mkt,
        "series_used": series_used,
        "performance": stats
    })


@app.route("/api/candles")
def api_candles():
    """Returns recent closed candles for charting."""
    tf = request.args.get("timeframe", "15m")
    limit = int(request.args.get("limit", 60))
    candles = market_data.get_candles(timeframe=tf, limit=limit, closed_only=True)
    return jsonify({"timeframe": tf, "candles": candles})


@app.route("/api/indicators")
def api_indicators():
    """Computes and returns current multi-timeframe indicators."""
    mtf = market_data.get_multi_timeframe_candles(limit=60)
    analysis = TechnicalAnalysis.analyze_multi_timeframe(mtf)
    result = {}
    for tf, snap in analysis.items():
        result[tf] = snap.to_dict() if snap else None
    return jsonify(result)


@app.route("/api/market")
def api_market():
    """Returns active Kalshi market and orderbook."""
    active_mkt, series_used = kalshi.find_active_btc_market()
    orderbook = None
    if active_mkt and active_mkt.get("ticker"):
        orderbook = kalshi.get_market_orderbook(active_mkt["ticker"])

    return jsonify({
        "market": active_mkt,
        "series": series_used,
        "orderbook": orderbook
    })


@app.route("/api/signals")
def api_signals():
    """Returns list of recent signals."""
    limit = int(request.args.get("limit", 30))
    signals = db.get_recent_signals(limit=limit)
    return jsonify({"signals": signals})


@app.route("/api/performance")
def api_performance():
    """Returns performance breakdown."""
    stats = perf_tracker.calculate_stats().to_dict()
    return jsonify(stats)


@app.route("/api/logs")
def api_logs():
    """Returns latest system activity logs."""
    logs = db.get_recent_logs(limit=50)
    return jsonify({"logs": logs})


@app.route("/api/trigger_cycle", methods=["POST"])
def api_trigger_cycle():
    """Manually triggers an immediate analysis cycle from the dashboard."""
    try:
        from app.telegram_bot import TelegramBot
        from app.scheduler import AnalysisScheduler

        bot = TelegramBot(settings, db, market_data, kalshi, signal_engine)
        sched = AnalysisScheduler(settings, db, market_data, kalshi, signal_engine, bot)
        sched.execute_cycle(force_broadcast=True)
        return jsonify({"status": "SUCCESS", "message": "Ciclo de análisis ejecutado exitosamente."})
    except Exception as e:
        return jsonify({"status": "ERROR", "message": str(e)}), 500


def run_dashboard():
    """Starts the Flask server."""
    app.run(
        host=settings.dashboard_host,
        port=settings.dashboard_port,
        debug=settings.dashboard_debug
    )


if __name__ == "__main__":
    run_dashboard()
