import sqlite3
import logging
from config import DB_PATH

logger = logging.getLogger(__name__)

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    """Ma'lumotlar bazasini yaratish yoki mavjudligini tekshirish."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS posted_news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                title TEXT,
                category TEXT,
                published_at TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_url ON posted_news(url)")
        conn.commit()
    logger.info("Ma'lumotlar bazasi tayyor.")

def is_news_posted(url: str) -> bool:
    """Xabar avval kanalga yuborilgan yoki yo'qligini tekshirish."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM posted_news WHERE url = ?", (url,))
        return cursor.fetchone() is not None

def add_news(url: str, title: str, category: str, published_at: str):
    """Yuborilgan xabarni bazaga qo'shish."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO posted_news (url, title, category, published_at)
                VALUES (?, ?, ?, ?)
            """, (url, title, category, published_at))
            conn.commit()
    except Exception as e:
        logger.error(f"Bazaga yozishda xatolik: {e}")

def get_stats() -> dict:
    """Admin uchun statistika olish."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM posted_news")
        total_count = cursor.fetchone()[0]

        cursor.execute("SELECT title, published_at, created_at FROM posted_news ORDER BY id DESC LIMIT 1")
        last_news = cursor.fetchone()

        return {
            "total_count": total_count,
            "last_news": last_news
        }

