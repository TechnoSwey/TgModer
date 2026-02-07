import os
from typing import List

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not found")

SENIOR_ADMIN_IDS: List[int] = [5874147280]

SPAM_THRESHOLD = 2
MUTE_DURATION = 300
STICKER_SPAM_THRESHOLD = 3
STICKER_TIME_WINDOW = 10
DEBUG = False
DATABASE_PATH = "bot_database.db"
DEFAULT_MUTE_TIME = 3600

LEVELS = {
    1: "👤 Обычный пользователь",
    2: "💰 Донатер",
    3: "🛡️ Младший модератор",
    4: "🛡️ Модератор",
    5: "👑 Младший админ",
    6: "👑 Старший админ"
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
LEVELS_FILE = os.path.join(DATA_DIR, "user_levels.json")
os.makedirs(DATA_DIR, exist_ok=True)
