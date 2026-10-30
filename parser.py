import aiohttp
import xml.etree.ElementTree as ET
import re
import html
import urllib.parse
from datetime import datetime
from email.utils import parsedate_to_datetime
import logging
from config import CHANNEL_USERNAME

logger = logging.getLogger(__name__)

RSS_URL = "https://kun.uz/news/rss"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

CATEGORY_MAP = {
    "jahon": "🌍 #Jahon",
    "oʻzbekiston": "🇺🇿 #Ozbekiston",
    "o'zbekiston": "🇺🇿 #Ozbekiston",
    "ozbekiston": "🇺🇿 #Ozbekiston",
    "iqtisodiyot": "💼 #Iqtisodiyot",
    "jamiyat": "👥 #Jamiyat",
    "sport": "⚽ #Sport",
    "fan-texnika": "💻 #Texnologiya",
    "texnologiya": "💻 #Texnologiya",
    "madaniyat": "🎭 #Madaniyat",
    "nuqtayi nazar": "🎙 #Tahlil",
    "intervyu": "🎙 #Intervyu",
    "avto": "🚗 #Avto"
}

MONTHS_UZ = {
    1: "yanvar", 2: "fevral", 3: "mart", 4: "aprel",
    5: "may", 6: "iyun", 7: "iyul", 8: "avgust",
    9: "sentabr", 10: "oktabr", 11: "noyabr", 12: "dekabr"
}

def clean_html(raw_html: str) -> str:
    """HTML teglar va ortiqcha belgilarni tozalash."""
    if not raw_html:
        return ""
    text = re.sub(r"<[^>]+>", "", raw_html)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def format_date(pub_date_str: str) -> str:
    """RSS sanasini chiroyli o'zbekcha formatga o'tkazish."""
    if not pub_date_str:
        return ""
    try:
        dt = parsedate_to_datetime(pub_date_str)
        month_name = MONTHS_UZ.get(dt.month, "")
        return f"{dt.day}-{month_name}, {dt.strftime('%H:%M')}"
    except Exception:
        return pub_date_str

def get_category_badge(cat_raw: str) -> str:
    if not cat_raw:
        return "⚡️ #Yangiliklar"
    key = cat_raw.strip().lower()
    if key in CATEGORY_MAP:
        return CATEGORY_MAP[key]
    clean_cat = re.sub(r"[^\w]", "", cat_raw.strip())
    return f"🏷 #{clean_cat}" if clean_cat else "⚡️ #Yangiliklar"

async def fetch_og_image(session: aiohttp.ClientSession, url: str) -> str | None:
    """Maqolaning asl katta rasmini (og:image) tortib olish."""
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=6)) as response:
            if response.status == 200:
                html_text = await response.text()
                # og:image meta tegini qidirish
                m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html_text, re.IGNORECASE)
                if not m:
                    m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', html_text, re.IGNORECASE)
                if m:
                    img_url = m.group(1).strip()
                    if img_url.startswith("//"):
                        img_url = "https:" + img_url
                    return img_url
    except Exception as e:
        logger.debug(f"og:image yuklashda xatolik ({url}): {e}")
    return None

def build_caption(title: str, description: str, category_badge: str, formatted_date: str) -> str:
    """Telegram uchun rasm tagidagi chiroyli caption yaratish (max 1024 belgi)."""
    clean_title = clean_html(title)
    clean_desc = clean_html(description)

    # Sana va rukn sarlavhasi
    header_parts = []
    if category_badge:
        header_parts.append(category_badge)
    if formatted_date:
        header_parts.append(f"🗓 {formatted_date}")
    header = " | ".join(header_parts)

    footer = ""
    if CHANNEL_USERNAME:
        footer = f"\n\n👉 <b>Obuna bo‘ling:</b> {CHANNEL_USERNAME}"

    # Telegram HTML uchun xavfsiz qilish va 1024 belgidan oshib ketmasligini ta'minlash
    # Qolip: {header}\n\n<b>{safe_title}</b>\n\n{safe_desc}{footer}
    fixed_len = len(header) + len(clean_title) + len(footer) + 20
    max_desc_len = max(0, 1000 - fixed_len)

    if len(clean_desc) > max_desc_len:
        if max_desc_len > 30:
            clean_desc = clean_desc[:max_desc_len - 3].rstrip() + "..."
        else:
            clean_desc = ""

    safe_title = html.escape(clean_title)
    safe_desc = html.escape(clean_desc)

    caption = f"{header}\n\n<b>{safe_title}</b>"
    if safe_desc:
        caption += f"\n\n{safe_desc}"
    if footer:
        caption += footer

    return caption

async def get_latest_news() -> list[dict]:
    """Kun.uz RSS manzilidan eng so'nggi yangiliklarni yuklab olish."""
    articles = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(RSS_URL, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=12)) as response:
                if response.status != 200:
                    logger.error(f"Kun.uz RSS xatosi: status {response.status}")
                    return articles

                xml_data = await response.text()
                root = ET.fromstring(xml_data)
                items = root.findall(".//item")

                for item in items:
                    link = item.findtext("link", "").strip()
                    title = item.findtext("title", "").strip()
                    desc = item.findtext("description", "").strip()
                    category_raw = item.findtext("category", "").strip()
                    pub_date_raw = item.findtext("pubDate", "").strip()

                    if not link or not title:
                        continue

                    # Maqola rasmini olish
                    image_url = await fetch_og_image(session, link)

                    badge = get_category_badge(category_raw)
                    date_formatted = format_date(pub_date_raw)
                    caption = build_caption(title, desc, badge, date_formatted)

                    # Do'stlarga ulashish havolasi
                    share_text = urllib.parse.quote(f"{clean_html(title)}\n\n{link}")
                    share_url = f"https://t.me/share/url?url={link}&text={share_text}"

                    articles.append({
                        "url": link,
                        "title": clean_html(title),
                        "description": clean_html(desc),
                        "category": category_raw,
                        "category_badge": badge,
                        "pub_date": pub_date_raw,
                        "formatted_date": date_formatted,
                        "image_url": image_url,
                        "caption": caption,
                        "share_url": share_url
                    })

    except Exception as e:
        logger.error(f"Yangiliklarni yuklashda xatolik yuz berdi: {e}", exc_info=True)

    return articles

