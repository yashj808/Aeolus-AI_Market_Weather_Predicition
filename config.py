import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# App Config
PORT = int(os.getenv("PORT", "8000"))
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///weather_agent.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
RUN_INTERVAL_HOURS = int(os.getenv("RUN_INTERVAL_HOURS", "4"))

# API Keys
APIFY_TOKEN = os.getenv("APIFY_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# If we are missing key API tokens, default to MOCK_MODE = True
# Users can explicitly disable mock mode with MOCK_MODE=False in env.
_mock_mode_default = "true" if not (APIFY_TOKEN and GEMINI_API_KEY) else "false"
MOCK_MODE = os.getenv("MOCK_MODE", _mock_mode_default).lower() == "true"

# Risk Parameters
INITIAL_BANKROLL = float(os.getenv("INITIAL_BANKROLL", "1000.0"))
KELLY_FRACTION = float(os.getenv("KELLY_FRACTION", "0.5"))  # half-Kelly
MAX_BET_PCT = float(os.getenv("MAX_BET_PCT", "0.05"))        # 5% max bet
MIN_EV_THRESHOLD = float(os.getenv("MIN_EV_THRESHOLD", "0.03"))  # 3% edge
MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.60"))  # 60% confidence gate
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "10"))
MAX_CORR_POS = int(os.getenv("MAX_CORR_POS", "3"))           # max positions per city
DAILY_LOSS_LIMIT_PCT = float(os.getenv("DAILY_LOSS_LIMIT_PCT", "0.15")) # 15% bankroll limit
POLYMARKET_CLOB_URL = os.getenv("POLYMARKET_CLOB_URL", "https://clob.polymarket.com")
POLYMARKET_GAMMA_URL = os.getenv("POLYMARKET_GAMMA_URL", "https://gamma-api.polymarket.com")
MIN_VOLUME_USD = float(os.getenv("POLYMARKET_MIN_VOLUME_USD", "500.0"))

# Telegram Notifications
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true" and bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
