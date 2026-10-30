import asyncio
import logging
import sys
import os
import html
from datetime import datetime

# Windows terminalida emoji va o'zbekcha belgilarni to'g'ri ko'rsatish
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

import config
from database import init_db, is_news_posted, add_news, get_stats
from parser import get_latest_news

# Log sozlamalari
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("KunUzBot")

# Bot va Dispatcher yaratish
dp = Dispatcher()

def create_article_keyboard(article_url: str, share_url: str) -> InlineKeyboardMarkup:
    """Maqola uchun chiroyli inline tugmalar."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🌐 Kun.uz'da o‘qish", url=article_url),
                InlineKeyboardButton(text="↗️ Ulashish", url=share_url)
            ]
        ]
    )
    return keyboard

async def publish_news(bot: Bot, force_all: bool = False) -> int:
    """
    Kun.uz dan yangiliklarni tekshirib, kanalga joylash.
    Qaytaradi: yuborilgan yangi maqolalar soni.
    """
    if not config.CHANNEL_ID:
        logger.warning("CHANNEL_ID ko'rsatilmagan! .env faylini tekshiring.")
        return 0

    articles = await get_latest_news()
    if not articles:
        return 0

    # Bazada bormi-yo'qligini tekshiramiz
    new_articles = [art for art in articles if not is_news_posted(art["url"])]

    if not new_articles:
        return 0

    # Agar baza butunlay bo'sh bo'lsa (birinchi marta ishga tushganda),
    # kanalni 15 ta xabar bilan birdan to'ldirib tashlamaslik uchun
    # oxirgi 2 tasini yuborib, qolganlarini bazada "o'qilgan" deb belgilaymiz.
    db_stats = get_stats()
    to_skip = []
    if db_stats["total_count"] == 0 and not force_all:
        logger.info(f"Birinchi ishga tushish: {len(new_articles)} ta yangilik topildi.")
        to_post = new_articles[:2]
        to_skip = new_articles[2:]
        new_articles = to_post

    # Eng eskisidan yangisiga qarab xronologik tartibda chiqarish
    new_articles.reverse()

    posted_count = 0
    for art in new_articles:
        keyboard = create_article_keyboard(art["url"], art["share_url"])
        msg_sent = False

        # 1. Rasm bilan yuborishga urinish
        if art.get("image_url"):
            try:
                await bot.send_photo(
                    chat_id=config.CHANNEL_ID,
                    photo=art["image_url"],
                    caption=art["caption"],
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard
                )
                msg_sent = True
                logger.info(f"Kanalga rasm bilan joylandi: {art['title'][:40]}...")
            except Exception as e:
                logger.warning(f"Rasm bilan yuborib bo'lmadi ({e}), matn ko'rinishida yuboriladi...")

        # 2. Agar rasmsiz bo'lsa yoki rasm yuklanmay qolsa, matn ko'rinishida yuborish
        if not msg_sent:
            try:
                await bot.send_message(
                    chat_id=config.CHANNEL_ID,
                    text=art["caption"],
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                    disable_web_page_preview=False
                )
                msg_sent = True
                logger.info(f"Kanalga matn sifatida joylandi: {art['title'][:40]}...")
            except Exception as e:
                logger.error(f"Xabarni kanalga yuborishda xatolik: {e}")

        # Agar muvaffaqiyatli yuborilgan bo'lsa, bazaga qayd etamiz
        if msg_sent:
            add_news(art["url"], art["title"], art["category"], art["pub_date"])
            posted_count += 1
            # Telegram limiti va spamlarning oldini olish uchun 3 soniya kutish
            await asyncio.sleep(3)

    # Agar birinchi marta muvaffaqiyatli post yuborilgan bo'lsa, qolgan eski yangiliklarni bazada belgilab qo'yamiz
    if posted_count > 0 and to_skip:
        for art in to_skip:
            add_news(art["url"], art["title"], art["category"], art["pub_date"])

    return posted_count

async def news_background_loop(bot: Bot):
    """Orqa fonda muntazam yangiliklarni tekshirib turuvchi asinxron sikl."""
    logger.info(f"Avtomatik tekshiruv ishga tushdi (Har {config.CHECK_INTERVAL} soniyada).")
    while True:
        try:
            posted = await publish_news(bot)
            if posted > 0:
                logger.info(f"{posted} ta yangi xabar kanalga joylandi.")
        except Exception as e:
            logger.error(f"Orqa fon siklida kutilmagan xatolik: {e}", exc_info=True)

        await asyncio.sleep(config.CHECK_INTERVAL)

# ==================== BUYRUQLAR (HANDLERS) ====================

@dp.message(CommandStart())
async def handle_start(message: types.Message):
    """Foydalanuvchi yoki admin uchun start xabari."""
    user_name = message.from_user.first_name or "Foydalanuvchi"
    stats = get_stats()

    text = (
        f"Assalomu alaykum, <b>{user_name}</b>!\n\n"
        f"🤖 Ushbu bot <b>Kun.uz</b> saytidagi eng so'nggi yangiliklarni "
        f"avtomatik tarzda Telegram kanalingizga professional formatda joylab boradi.\n\n"
        f"⚙️ <b>Kanal:</b> <code>{config.CHANNEL_ID or 'Ulanmagan'}</code>\n"
        f"⏱ <b>Interval:</b> har {config.CHECK_INTERVAL} soniyada\n"
        f"📊 <b>Kanalga tashlangan postlar:</b> {stats['total_count']} ta\n\n"
        f"<b>Buyruqlar:</b>\n"
        f"🔹 /status - Bot statistikasi va holati\n"
        f"🔹 /check - Yangiliklarni hoziroq majburiy tekshirish"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)

@dp.message(Command("status", "stats"))
async def handle_status(message: types.Message):
    """Bot va baza statistikasini ko'rsatish."""
    stats = get_stats()
    last = stats.get("last_news")

    last_title = last[0] if last else "Hali yangilik yo'q"
    last_time = last[1] if last else "-"

    text = (
        f"📊 <b>Bot Holati va Statistikasi:</b>\n\n"
        f"📢 <b>Ulangan kanal:</b> <code>{config.CHANNEL_ID}</code>\n"
        f"📝 <b>Jami yuborilgan xabarlar:</b> <code>{stats['total_count']} ta</code>\n"
        f"⏰ <b>Tekshirish davriyligi:</b> <code>har {config.CHECK_INTERVAL} soniya</code>\n"
        f"📌 <b>So'nggi post:</b> {last_title}\n"
        f"🕒 <b>Nashr vaqti:</b> {last_time}\n\n"
        f"🟢 Bot faol va uzluksiz ishlamoqda."
    )
    await message.answer(text, parse_mode=ParseMode.HTML)

@dp.message(Command("check", "check_now"))
async def handle_check_now(message: types.Message, bot: Bot):
    """Qo'lda darhol yangiliklarni tekshirish buyrug'i."""
    wait_msg = await message.answer("🔄 Kun.uz tekshirilmoqda, kuting...")
    try:
        count = await publish_news(bot)
        if count > 0:
            await wait_msg.edit_text(f"✅ Tekshiruv muvaffaqiyatli: <b>{count} ta yangi maqola</b> kanalga joylandi!", parse_mode=ParseMode.HTML)
        else:
            await wait_msg.edit_text("ℹ️ Hozircha yangi maqolalar yo'q. Barcha xabarlar allaqachon kanalga joylangan.", parse_mode=ParseMode.HTML)
    except Exception as e:
        await wait_msg.edit_text(f"❌ Xatolik yuz berdi: <code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)

# ==================== ASOSIY ISHGA TUSHIRISH ====================

async def main():
    if not config.BOT_TOKEN:
        print("\n❌ XATOLIK: BOT_TOKEN topilmadi!")
        print("Iltimos, .env fayliga Telegram Bot tokeningizni kiriting:\nBOT_TOKEN=123456789:ABCDEF...\n")
        return

    # Bazani ishga tushirish
    init_db()

    # Botni ishga tushirish
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    try:
        bot_info = await bot.get_me()
        print("=" * 60)
        print(f"🚀 Bot muvaffaqiyatli ishga tushdi: @{bot_info.username}")
        print(f"📢 Nishon kanal: {config.CHANNEL_ID}")
        print(f"⏱ Tekshirish oralig'i: {config.CHECK_INTERVAL} sekund")
        print("=" * 60)

        # Kanalga admin ekanligini tekshirish
        try:
            member = await bot.get_chat_member(chat_id=config.CHANNEL_ID, user_id=bot_info.id)
            if member.status not in ["administrator", "creator"]:
                logger.warning(f"⚠️ DIQQAT: @{bot_info.username} boti {config.CHANNEL_ID} kanalida ADMIN emas! (Status: {member.status}). Xabar yuborish uchun kanalga admin qilib qo'shing.")
            else:
                logger.info(f"✅ Bot {config.CHANNEL_ID} kanalida admin huquqiga ega.")
        except Exception as ce:
            logger.warning(f"⚠️ DIQQAT: @{bot_info.username} boti {config.CHANNEL_ID} kanalida a'zo/admin emas ({ce}). Iltimos, botni kanalga admin qilib qo'shing!")
    except Exception as e:
        print(f"❌ Bot tokenida xatolik: {e}")
        return

    # Agar bulutli hosting PORT bersa (masalan, Render.com)
    if os.getenv("PORT"):
        try:
            from aiohttp import web
            health_app = web.Application()
            health_app.router.add_get("/", lambda r: web.Response(text="Bot 24/7 ishlab turibdi ✅"))
            health_app.router.add_get("/health", lambda r: web.Response(text="OK"))
            port = int(os.getenv("PORT", "8080"))
            runner = web.AppRunner(health_app)
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", port)
            await site.start()
            logger.info(f"Bulutli platforma uchun Health check server ishga tushdi (port {port}).")
        except Exception as e:
            logger.warning(f"Health serverni ishga tushirib bo'lmadi: {e}")

    # Orqa fon vazifasini ishga tushirish
    asyncio.create_task(news_background_loop(bot))

    # Xabarlarni qabul qilish (polling)
    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")

