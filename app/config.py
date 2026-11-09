"""Configuration module for BTC SCALPING AI."""

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv

# Root directory of the repository
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file
load_dotenv(dotenv_path=BASE_DIR / ".env")


def _get_bool(env_var: str, default: bool = False) -> bool:
    val = os.getenv(env_var)
    if val is None:
        return default
    return str(val).strip().lower() in ("true", "1", "yes", "y", "t")


def _get_list(env_var: str, default: str) -> List[str]:
    raw = os.getenv(env_var, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _get_int_list(env_var: str) -> List[int]:
    raw = os.getenv(env_var, "")
    result = []
    for item in raw.split(","):
        item = item.strip()
        if item.isdigit():
            result.append(int(item))
    return result


@dataclass
class Settings:
    # Kalshi Configuration
    kalshi_api_url: str = os.getenv("KALSHI_API_URL", "https://api.elections.kalshi.com/trade-api/v2").rstrip("/")
    kalshi_target_series: str = os.getenv("KALSHI_TARGET_SERIES", "KXBTC15M")
    kalshi_fallback_series: List[str] = field(
        default_factory=lambda: _get_list("KALSHI_FALLBACK_SERIES", "KXBTCH,KXBTCD,KXBTC")
    )
    kalshi_key_id: str = os.getenv("KALSHI_KEY_ID", "")
    kalshi_private_key_path: str = os.getenv("KALSHI_PRIVATE_KEY_PATH", "")
    kalshi_email: str = os.getenv("KALSHI_EMAIL", "")
    kalshi_password: str = os.getenv("KALSHI_PASSWORD", "")

    # Telegram Bot Configuration
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    telegram_authorized_users: List[int] = field(
        default_factory=lambda: _get_int_list("TELEGRAM_AUTHORIZED_USERS")
    )

    # Core Parameters
    analysis_interval_minutes: int = int(os.getenv("ANALYSIS_INTERVAL_MINUTES", "15"))
    signal_window_minutes: int = int(os.getenv("SIGNAL_WINDOW_MINUTES", "6"))
    scan_interval_seconds: int = int(os.getenv("SCAN_INTERVAL_SECONDS", "15"))
    min_confidence_score: int = int(os.getenv("MIN_CONFIDENCE_SCORE", "60"))
    mode: str = os.getenv("MODE", "SOLO_SEÑALES")

    # Database & Paths
    database_path: Path = BASE_DIR / os.getenv("DATABASE_PATH", "data/btc_scalping.db")
    logs_dir: Path = BASE_DIR / "logs"
    data_dir: Path = BASE_DIR / "data"

    # Dashboard
    dashboard_host: str = os.getenv("DASHBOARD_HOST", "127.0.0.1")
    dashboard_port: int = int(os.getenv("DASHBOARD_PORT", "8080"))
    dashboard_debug: bool = _get_bool("DASHBOARD_DEBUG", False)

    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()

    def __post_init__(self):
        # In serverless environments (like Vercel / AWS Lambda), the source directory is read-only
        is_serverless = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))
        if is_serverless or not os.access(str(BASE_DIR), os.W_OK):
            self.data_dir = Path("/tmp/data")
            self.logs_dir = Path("/tmp/logs")
            if not os.getenv("DATABASE_PATH"):
                self.database_path = self.data_dir / "btc_scalping.db"

        # Safely ensure directories exist without crashing on read-only file systems
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            self.data_dir = Path("/tmp/data")
            self.data_dir.mkdir(parents=True, exist_ok=True)

        try:
            self.logs_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            self.logs_dir = Path("/tmp/logs")
            self.logs_dir.mkdir(parents=True, exist_ok=True)

    def is_user_authorized(self, user_id: int) -> bool:
        """Checks if a Telegram user is authorized. If list is empty, allows chat_id or all."""
        if not self.telegram_authorized_users:
            # If explicit chat_id is defined and user_id matches or no restriction
            if self.telegram_chat_id and str(user_id) == str(self.telegram_chat_id):
                return True
            return True  # Open if no restrictions specified
        return user_id in self.telegram_authorized_users

    def get_private_key_pem(self) -> Optional[str]:
        """Loads RSA private key without leaking sensitive paths."""
        if self.kalshi_private_key_path:
            p = Path(self.kalshi_private_key_path).expanduser().resolve()
            if p.exists() and p.is_file():
                return p.read_text(encoding="utf-8")
        return None


settings = Settings()

