import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# .env faylini yuklash
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHANNEL_ID = os.getenv("CHANNEL_ID", "").strip()
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "").strip()
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "60"))
ADMIN_ID = os.getenv("ADMIN_ID", "").strip()
DB_PATH = str(BASE_DIR / os.getenv("DB_PATH", "kunuz_news.db"))

# Agar CHANNEL_USERNAME @ bilan boshlanmagan bo'lsa va kiritilgan bo'lsa, @ qo'shish
if CHANNEL_USERNAME and not CHANNEL_USERNAME.startswith("@") and not CHANNEL_USERNAME.startswith("https://"):
    CHANNEL_USERNAME = f"@{CHANNEL_USERNAME}"

