"""Telegram Bot integration for BTC SCALPING AI.
Supports command handling (/start, /status, /btc, /signal, /market, /history, /performance, /help)
and formatted 15-minute alert broadcasts.
"""

from datetime import datetime, timezone
import html
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional
import requests

from app.config import Settings

logger = logging.getLogger("TelegramBot")


class TelegramBot:
    """Manages Telegram Bot notifications and interactive commands."""

    def __init__(self, settings: Settings, db=None, market_data=None, kalshi=None, signal_engine=None):
        self.settings = settings
        self.db = db
        self.market_data = market_data
        self.kalshi = kalshi
        self.signal_engine = signal_engine

        self.token = settings.telegram_bot_token.strip()
        self.chat_id = str(settings.telegram_chat_id).strip()
        self.base_url = f"https://api.telegram.org/bot{self.token}" if self.token else ""

        self._running = False
        self._polling_thread: Optional[threading.Thread] = None
        self._last_update_id = 0

    @property
    def is_configured(self) -> bool:
        """Returns True if bot token is configured."""
        return bool(self.token and len(self.token) > 10)

    def send_message(self, text: str, parse_mode: Optional[str] = "HTML", target_chat_id: Optional[str] = None) -> bool:
        """Sends a text message to configured or specified chat."""
        if not self.is_configured:
            logger.debug("Telegram bot token not configured. Skipping message dispatch.")
            return False

        chat = target_chat_id or self.chat_id
        if not chat:
            logger.warning("No Telegram chat_id configured.")
            return False

        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": chat,
            "text": text,
            "disable_web_page_preview": True
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        try:
            resp = requests.post(url, json=payload, timeout=8)
            if resp.status_code == 200:
                return True
            else:
                logger.error(f"Telegram API error ({resp.status_code}): {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

    def format_signal_report(
        self,
        signal_decision: Any,
        kalshi_market: Optional[Dict[str, Any]],
        indicators: Dict[str, Any]
    ) -> str:
        """Formats the periodic 15-minute report according to Section 8 specifications."""
        sig = signal_decision
        mkt_ticker = sig.market_ticker if sig else "N/A"
        btc_price_str = f"${sig.btc_price:,.2f}" if sig and sig.btc_price else "N/A"

        # Format Indicators
        trend = indicators.get("trend", "N/A")
        rsi = f"{indicators.get('rsi_14', 0):.1f}" if "rsi_14" in indicators else "N/A"
        ema9 = f"${indicators.get('ema_9', 0):,.2f}" if "ema_9" in indicators else "N/A"
        ema21 = f"${indicators.get('ema_21', 0):,.2f}" if "ema_21" in indicators else "N/A"
        ema50 = f"${indicators.get('ema_50', 0):,.2f}" if "ema_50" in indicators else "N/A"
        macd = f"{indicators.get('macd_histogram', 0):+.2f}" if "macd_histogram" in indicators else "N/A"

        vol_conf = "Confirmado" if indicators.get("volume_confirmed") else "Normal/Bajo"
        if indicators.get("volume_abnormal"):
            vol_conf += " (ANORMAL)"

        # Prices
        yes_price = f"{kalshi_market.get('yes_ask', 'N/A')}¢" if kalshi_market and kalshi_market.get('yes_ask') is not None else "N/A"
        no_price = f"{kalshi_market.get('no_ask', 'N/A')}¢" if kalshi_market and kalshi_market.get('no_ask') is not None else "N/A"
        time_rem = kalshi_market.get("time_remaining_str", "N/A") if kalshi_market else (sig.time_remaining_str if sig else "N/A")

        sig_type = sig.signal_type if sig else "WAIT"
        conf_str = f"{sig.confidence_score:.1f}% (Puntuación heurística de modelo)" if sig else "0.0%"
        justification = sig.technical_justification if sig else "Evaluando condiciones de mercado."

        # Check if inside 6-minute window
        sec_rem = kalshi_market.get("seconds_remaining", 0) if kalshi_market else 0
        window_badge = ""
        if 0 < sec_rem <= 360:
            window_badge = "⚡ <b>VENTANA SCALPING: ÚLTIMOS 6 MINUTOS</b> ⏳\n\n"

        to_beat_str = f"${kalshi_market['strike_price']:,.2f}" if kalshi_market and kalshi_market.get("strike_price") else "N/A"

        # Plain text adhering to exact specification
        report = (
            f"{window_badge}"
            f"<b>BTC SCALPING AI</b>\n\n"
            f"<b>Mercado:</b> BTC / USDT\n"
            f"<b>Plataforma:</b> KALSHI\n"
            f"<b>Contrato:</b> {mkt_ticker}\n"
            f"<b>TO BEAT (Strike):</b> {to_beat_str}\n\n"
            f"<b>Precio BTC (NOW):</b> {btc_price_str}\n"
            f"<b>Tendencia:</b> {trend}\n"
            f"<b>RSI:</b> {rsi}\n"
            f"<b>EMA 9:</b> {ema9}\n"
            f"<b>EMA 21:</b> {ema21}\n"
            f"<b>EMA 50:</b> {ema50}\n"
            f"<b>MACD:</b> {macd}\n"
            f"<b>Volumen:</b> {vol_conf}\n\n"
            f"<b>SEÑAL:</b> <code>{sig_type}</code>\n\n"
            f"<b>Precio YES:</b> {yes_price}\n"
            f"<b>Precio NO:</b> {no_price}\n"
            f"<b>Tiempo restante:</b> {time_rem}\n\n"
            f"<b>Confianza del modelo:</b> {conf_str}\n"
            f"<b>Justificación técnica:</b> {html.escape(justification)}\n\n"
            f"<b>Modo:</b> SOLO SEÑALES."
        )
        return report

    def broadcast_signal_if_new(
        self,
        signal_decision: Any,
        kalshi_market: Optional[Dict[str, Any]],
        indicators: Dict[str, Any],
        force: bool = False
    ) -> bool:
        """Sends signal only if it's confirmed or forced, avoiding duplicate alerts."""
        if not self.is_configured:
            return False

        # If it's a WAIT signal and not forced, we don't spam notifications unless configured
        if not force and signal_decision.signal_type == "WAIT":
            logger.debug("Suppressing Telegram alert for neutral WAIT signal to avoid alert spam.")
            return False

        text = self.format_signal_report(signal_decision, kalshi_market, indicators)
        return self.send_message(text)

    # --- Interactive Bot Commands ---

    def start_polling(self) -> None:
        """Starts background thread to poll Telegram for user commands."""
        if not self.is_configured:
            logger.info("Telegram Bot token missing; command listener not started.")
            return

        self._running = True
        self._polling_thread = threading.Thread(target=self._poll_updates, daemon=True, name="TelegramPollThread")
        self._polling_thread.start()
        logger.info("Telegram command polling listener started.")

    def stop_polling(self) -> None:
        """Stops background polling."""
        self._running = False

    def _poll_updates(self) -> None:
        """Continuously polls for incoming commands with authentication checks."""
        while self._running:
            try:
                url = f"{self.base_url}/getUpdates"
                params = {"offset": self._last_update_id + 1, "timeout": 15}
                resp = requests.get(url, params=params, timeout=20)
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("result", []):
                        self._last_update_id = item.get("update_id", self._last_update_id)
                        message = item.get("message")
                        if message and "text" in message:
                            self._handle_incoming_message(message)
                time.sleep(1)
            except Exception as e:
                logger.debug(f"Error in Telegram long polling: {e}")
                time.sleep(3)

    def _handle_incoming_message(self, message: Dict[str, Any]) -> None:
        """Verifies authorization and routes commands."""
        user = message.get("from", {})
        user_id = user.get("id", 0)
        chat_id = str(message.get("chat", {}).get("id", ""))
        text = message.get("text", "").strip()

        # Security check: verify user authorization
        if not self.settings.is_user_authorized(user_id):
            logger.warning(f"Unauthorized access attempt from user_id: {user_id}")
            self.send_message("⛔ Acceso denegado: Usuario no autorizado en este bot.", target_chat_id=chat_id)
            return

        # Route command
        cmd = text.split()[0].lower()
        if cmd == "/start":
            self._cmd_start(chat_id)
        elif cmd == "/help":
            self._cmd_help(chat_id)
        elif cmd == "/status":
            self._cmd_status(chat_id)
        elif cmd == "/btc":
            self._cmd_btc(chat_id)
        elif cmd == "/signal":
            self._cmd_signal(chat_id)
        elif cmd == "/market":
            self._cmd_market(chat_id)
        elif cmd == "/history":
            self._cmd_history(chat_id)
        elif cmd == "/performance":
            self._cmd_performance(chat_id)
        else:
            self.send_message(f"Comando no reconocido: {cmd}. Usa /help para ver los comandos.", target_chat_id=chat_id)

    # --- Command Implementations ---

    def _cmd_start(self, chat_id: str) -> None:
        msg = (
            "🚀 <b>BTC SCALPING AI</b> activo.\n\n"
            "Sistema autónomo de análisis técnico de Bitcoin y predicción para Kalshi.\n\n"
            "Usa /help para consultar los comandos disponibles."
        )
        self.send_message(msg, target_chat_id=chat_id)

    def _cmd_help(self, chat_id: str) -> None:
        msg = (
            "📋 <b>Comandos Disponibles:</b>\n\n"
            "• /status — Estado actual del bot y componentes\n"
            "• /btc — Precio actual y datos técnicos de BTC/USDT\n"
            "• /signal — Última señal generada (YES/NO/WAIT)\n"
            "• /market — Información del contrato activo en Kalshi\n"
            "• /history — Historial de las últimas 5 señales\n"
            "• /performance — Estadísticas históricas de rendimiento\n"
            "• /help — Muestra este menú de ayuda"
        )
        self.send_message(msg, target_chat_id=chat_id)

    def _cmd_status(self, chat_id: str) -> None:
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        msg = (
            f"⚙️ <b>Estado del Sistema:</b>\n\n"
            f"• <b>Modo:</b> {self.settings.mode}\n"
            f"• <b>Intervalo de análisis:</b> {self.settings.analysis_interval_minutes} minutos\n"
            f"• <b>Serie Kalshi:</b> {self.settings.kalshi_target_series}\n"
            f"• <b>Umbral confianza:</b> {self.settings.min_confidence_score}%\n"
            f"• <b>Base de datos:</b> Activa (SQLite)\n"
            f"• <b>Timestamp:</b> {now_str}"
        )
        self.send_message(msg, target_chat_id=chat_id)

    def _cmd_btc(self, chat_id: str) -> None:
        price = self.market_data.get_current_btc_price() if self.market_data else None
        if price:
            msg = f"🪙 <b>Precio Spot BTC/USDT:</b> <code>${price:,.2f}</code>"
        else:
            msg = "⚠️ No se pudo obtener el precio spot de Bitcoin en este momento."
        self.send_message(msg, target_chat_id=chat_id)

    def _cmd_signal(self, chat_id: str) -> None:
        if not self.db:
            self.send_message("Base de datos no inicializada.", target_chat_id=chat_id)
            return

        last_sig = self.db.get_latest_signal()
        if not last_sig:
            self.send_message("No hay señales registradas todavía.", target_chat_id=chat_id)
            return

        msg = (
            f"🎯 <b>Última Señal Registrada:</b>\n\n"
            f"• <b>Tipo:</b> <code>{last_sig['signal_type']}</code>\n"
            f"• <b>Mercado:</b> {last_sig['market_ticker']}\n"
            f"• <b>BTC al emitir:</b> ${last_sig['btc_price']:,.2f}\n"
            f"• <b>Confianza del modelo:</b> {last_sig['confidence_score']:.1f}%\n"
            f"• <b>Fecha:</b> {last_sig['timestamp']}\n\n"
            f"<b>Justificación:</b>\n{html.escape(last_sig.get('technical_justification') or 'N/A')}"
        )
        self.send_message(msg, target_chat_id=chat_id)

    def _cmd_market(self, chat_id: str) -> None:
        if not self.kalshi:
            self.send_message("Cliente Kalshi no disponible.", target_chat_id=chat_id)
            return

        market, series = self.kalshi.find_active_btc_market()
        if not market:
            self.send_message(f"⚠️ No hay contratos activos disponibles bajo la serie {self.settings.kalshi_target_series}.", target_chat_id=chat_id)
            return

        yes_p = f"{market.get('yes_ask', 'N/A')}¢"
        no_p = f"{market.get('no_ask', 'N/A')}¢"
        strike = f"${market['strike_price']:,.2f}" if market.get("strike_price") else "TBD"

        msg = (
            f"🏛️ <b>Contrato Kalshi Activo:</b>\n\n"
            f"• <b>Ticker:</b> <code>{market['ticker']}</code>\n"
            f"• <b>Título:</b> {market['title']}\n"
            f"• <b>Serie:</b> {series}\n"
            f"• <b>Strike objetivo:</b> {strike}\n"
            f"• <b>Precio YES:</b> {yes_p}\n"
            f"• <b>Precio NO:</b> {no_p}\n"
            f"• <b>Tiempo restante:</b> {market.get('time_remaining_str', 'N/A')}\n"
            f"• <b>Estado:</b> {market['status'].upper()}"
        )
        self.send_message(msg, target_chat_id=chat_id)

    def _cmd_history(self, chat_id: str) -> None:
        if not self.db:
            return
        signals = self.db.get_recent_signals(limit=5)
        if not signals:
            self.send_message("No hay historial de señales disponible.", target_chat_id=chat_id)
            return

        lines = ["📜 <b>Últimas Señales:</b>\n"]
        for s in signals:
            ts = s["timestamp"][:16].replace("T", " ")
            lines.append(f"• <b>{s['signal_type']}</b> | {s['market_ticker']} | BTC: ${s['btc_price']:,.0f} | Conf: {s['confidence_score']:.0f}% ({ts})")

        self.send_message("\n".join(lines), target_chat_id=chat_id)

    def _cmd_performance(self, chat_id: str) -> None:
        from app.performance import PerformanceTracker
        if not self.db:
            return

        tracker = PerformanceTracker(self.db)
        stats = tracker.calculate_stats()

        msg = (
            f"📊 <b>Rendimiento Histórico:</b>\n\n"
            f"• <b>Total Señales:</b> {stats.total_signals}\n"
            f"• <b>Señales YES:</b> {stats.yes_signals}\n"
            f"• <b>Señales NO:</b> {stats.no_signals}\n"
            f"• <b>Señales WAIT:</b> {stats.wait_signals}\n\n"
            f"• <b>Aciertos (Wins):</b> {stats.wins}\n"
            f"• <b>Errores (Losses):</b> {stats.losses}\n"
            f"• <b>Pendientes de evaluación:</b> {stats.pending_evaluations}\n"
            f"• <b>Tasa de Acierto:</b> <code>{stats.win_rate_percent:.1f}%</code>\n\n"
            f"<i>Nota: Las señales pendientes no se computan en la tasa de acierto.</i>"
        )
        self.send_message(msg, target_chat_id=chat_id)
