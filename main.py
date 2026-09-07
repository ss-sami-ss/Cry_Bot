# -*- coding: utf-8 -*-
"""
نقطه‌ی شروع ربات.
دو کار همزمان انجام می‌ده:
  1) هر چند دقیقه فید خبری رو چک می‌کنه و در صورت پیدا کردن خبر مهم، تحلیل می‌فرسته
  2) به پیام‌های کاربر (بررسی معامله ...) گوش می‌ده و محاسبه‌ی ریسک رو جواب می‌ده
"""

import datetime as dt
import logging
from zoneinfo import ZoneInfo

# فعال کردن لاگ‌های داخلی کتابخونه — این‌جوری اگه هر خطایی تو job های پس‌زمینه
# (مثل چک اخبار) رخ بده، پنهان نمی‌مونه و تو همون پنجره‌ی cmd چاپ می‌شه.
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
# لاگ‌های خیلی پرحجم کتابخونه‌ی httpx رو کم می‌کنیم که شلوغ نشه
logging.getLogger("httpx").setLevel(logging.WARNING)

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    CLOUDFLARE_WORKER_URL,
    AUTHORIZED_USER_IDS,
    NEWS_CHECK_INTERVAL_MINUTES,
    NEW_LISTINGS_CHECK_INTERVAL_MINUTES,
    HOT_MEME_CHECK_INTERVAL_MINUTES,
    DEFAULT_WATCHED_COINS,
    DAILY_DIGEST_HOURS,
    TIMEZONE,
)
from db import init_db, seed_watchlist_if_empty, get_user_settings, get_watchlist, get_meme_focus_users, toggle_meme_focus
from news import fetch_important_news, build_news_response, build_daily_digest
from new_listings import check_new_listings, build_new_listing_message
from meme_focus import scan_hot_meme_coins, build_hot_meme_message
from handlers import handle_message, handle_check_command
from debug_handlers import testnews_command
from recent_news_handlers import recent_news_command
from settings_handlers import (
    settings_command, settings_callback,
    receive_city_name, receive_city_tz, receive_toman_rate, cancel_settings,
    WAITING_CITY_NAME, WAITING_CITY_TZ, WAITING_TOMAN_RATE,
)
from tracking import track_callback, reschedule_pending_tracks
from technique_handlers import (
    techniques_menu_command, technique_selected, receive_coin_for_technique,
    cancel_technique, WAITING_COIN_FOR_TECHNIQUE,
)
from analysis_handlers import (
    start_standalone_analysis, receive_coin_for_analysis,
    cancel_standalone_analysis, WAITING_COIN_FOR_ANALYSIS,
)
from glossary_handlers import glossary_command
from watchlist_handlers import (
    watch_entry, watch_receive,
    unwatch_entry, unwatch_receive,
    cancel_watch, watchlist_command,
    WAITING_WATCH_SYMBOL, WAITING_UNWATCH_SYMBOL,
)
from cleanup_handlers import clearold_entry, clearold_receive, cancel_clearold, WAITING_DAYS
from auth_handlers import check_authorization

# کیبورد دائمی پایین صفحه — دسته‌بندی‌شده و با متن‌های هم‌طول تا تو موبایل هم منظم بمونه:
#   ردیف ۱: کارهای اصلی (محاسبه + دیدن لیست)
#   ردیف ۲: مدیریت واچ‌لیست (افزودن/حذف ارز)
#   ردیف ۳: اخبار (اخیر + تست فید)
#   ردیف ۴: نگهداری و تنظیمات
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["🧮 محاسبه معامله", "📋 واچ‌لیست"],
        ["➕ افزودن ارز", "➖ حذف ارز"],
        ["🕕 اخبار اخیر", "🔍 تست فید"],
        ["🧠 تکنیک‌ها", "🗑 پاک‌سازی"],
        ["🔬 تحلیل ارز", "📖 اصطلاحات"],
        ["🔥 میم‌کوین‌های داغ", "⚙️ تنظیمات"],
    ],
    resize_keyboard=True,
)
from conversation import (
    start_calc,
    start_calc_from_button,
    receive_code,
    receive_capital,
    receive_risk,
    cancel_calc,
    WAITING_CODE,
    WAITING_CAPITAL,
    WAITING_RISK,
)


async def broadcast_analysis_to_all(context: ContextTypes.DEFAULT_TYPE, item, coin):
    """
    برای یه خبر/ارز مشخص، به هر کاربر مجاز، پیام رو با تنظیمات و واچ‌لیستِ شخصی خودش می‌سازه و می‌فرسته.
    زیر پیام کامل (نه پیام کوتاه کشف)، دکمه‌ی «محاسبه معامله» هم می‌ذاره.
    """
    if not AUTHORIZED_USER_IDS:
        print("[هشدار] هیچ کاربر مجازی تنظیم نشده — نمی‌دونم پیام رو کجا بفرستم.")
        return

    for uid in AUTHORIZED_USER_IDS:
        try:
            settings = get_user_settings(uid)
            watchlist = get_watchlist(uid)
            text, code = build_news_response(item, coin, settings, watchlist)
            if not text:
                continue
            reply_markup = None
            if code:
                reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🧮 محاسبه معامله", callback_data=f"calc:{code}")]])
            await context.bot.send_message(chat_id=uid, text=text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception as e:
            print(f"[خطا در ارسال به {uid}] {e}")


async def broadcast_to_all(context: ContextTypes.DEFAULT_TYPE, text: str):
    """پیام ساده (بدون فرمت‌بندی شخصی) رو به همه‌ی کاربرهای مجاز می‌فرسته — مثل خلاصه‌ی روزانه."""
    if not AUTHORIZED_USER_IDS:
        print("[هشدار] هیچ کاربر مجازی تنظیم نشده — نمی‌دونم پیام رو کجا بفرستم.")
        return

    for uid in AUTHORIZED_USER_IDS:
        try:
            await context.bot.send_message(chat_id=uid, text=text)
        except Exception as e:
            print(f"[خطا در ارسال به {uid}] {e}")


async def check_news_job(context: ContextTypes.DEFAULT_TYPE):
    """این تابع به‌صورت دوره‌ای اجرا می‌شه (توسط job_queue) — هر چند دقیقه یه‌بار."""
    news_items = fetch_important_news()
    for item in news_items:
        for coin in item["coins"]:
            await broadcast_analysis_to_all(context, item, coin)


async def check_new_listings_job(context: ContextTypes.DEFAULT_TYPE):
    """
    هر چند دقیقه یه‌بار چک می‌کنه آیا نماد USDT جدیدی رو Binance لیست شده —
    ممکنه میم‌کوین تازه‌وارد باشه یا هر پروژه‌ی جدید دیگه‌ای. فقط برای کاربرهایی
    که «🔥 میم‌کوین‌های داغ» رو روشن کردن فرستاده می‌شه.
    """
    new_symbols = check_new_listings()
    if not new_symbols:
        return
    target_users = get_meme_focus_users(AUTHORIZED_USER_IDS)
    for symbol in new_symbols:
        message = build_new_listing_message(symbol)
        for uid in target_users:
            try:
                await context.bot.send_message(chat_id=uid, text=message)
            except Exception as e:
                print(f"[خطا در ارسال لیستینگ جدید به {uid}] {e}")


async def check_hot_meme_coins_job(context: ContextTypes.DEFAULT_TYPE):
    """
    هر چند دقیقه یه‌بار میم‌کوین‌های شناخته‌شده + لیستینگ‌های تازه رو از نظر
    نوسان غیرعادی چک می‌کنه. فقط برای کاربرهایی که تمرکز میم‌کوین رو روشن کردن.
    """
    target_users = get_meme_focus_users(AUTHORIZED_USER_IDS)
    if not target_users:
        return
    hot_coins = scan_hot_meme_coins()
    for hot_item in hot_coins:
        message = build_hot_meme_message(hot_item)
        for uid in target_users:
            try:
                await context.bot.send_message(chat_id=uid, text=message)
            except Exception as e:
                print(f"[خطا در ارسال میم‌کوین داغ به {uid}] {e}")


async def meme_focus_toggle_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دکمه‌ی «🔥 میم‌کوین‌های داغ» — با هر بار زدن، روشن/خاموش می‌شه (یه دکمه، هردو کار)."""
    user_id = update.effective_user.id
    new_state = toggle_meme_focus(user_id)
    if new_state:
        await update.message.reply_text(
            "🔥 تمرکز میم‌کوین‌های داغ روشن شد.\n\n"
            "از این به بعد، علاوه بر اخبار عادی، هروقت یه لیستینگ تازه رو Binance بیاد "
            "یا یه میم‌کوین نوسان غیرعادی (۱۵٪+ تو ۲۴ ساعت) داشته باشه، بهت خبر می‌دم.\n\n"
            "برای خاموش‌کردن، دوباره همین دکمه رو بزن."
        )
    else:
        await update.message.reply_text("🛑 تمرکز میم‌کوین‌های داغ خاموش شد — دیگه این اعلان‌ها نمیاد.")


async def daily_digest_job(context: ContextTypes.DEFAULT_TYPE):
    """این تابع در ساعت‌های ثابت (DAILY_DIGEST_HOURS) اجرا می‌شه — مستقل از خبر."""
    if not AUTHORIZED_USER_IDS:
        return
    for uid in AUTHORIZED_USER_IDS:
        try:
            settings = get_user_settings(uid)
            watchlist = get_watchlist(uid)
            digest = build_daily_digest(settings, watchlist)
            if digest:
                await context.bot.send_message(chat_id=uid, text=digest)
        except Exception as e:
            print(f"[خطا در ارسال خلاصه به {uid}] {e}")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ربات مانیتورینگ رمزارز فعاله ✅\n\n"
        "این ربات خودش خبرهای مهم رو با تحلیل فنی برات می‌فرسته، "
        "و هر روز هم یه خلاصه‌ی دوره‌ای از وضعیت بازار می‌ده.\n\n"
        "⚙️ از «تنظیمات» می‌تونی تقویم (شمسی/میلادی)، منطقه زمانی، و واحد پول "
        "(دلار/تومان) رو مطابق خودت تنظیم کنی.\n\n"
        "📌 بعد از هر محاسبه، دکمه‌ی «پیگیری» رو بزن تا بعد از گذشت افق زمانی "
        "پیشنهاد (نسبت به زمان انتشار خبر)، نتیجه‌ی واقعیش رو برات چک کنم.\n\n"
        "پایین صفحه یه کیبورد ثابت گذاشتم — دیگه نیازی به تایپ دستی نیست، "
        "فقط رو دکمه‌ها بزن.",
        reply_markup=MAIN_KEYBOARD,
    )


async def setup_bot_commands(app):
    """
    فقط لیست دستورات رو ثبت می‌کنه (که وقتی "/" تایپ می‌کنی پیشنهادها بیان).
    دیگه دستِ دکمه‌ی «Menu» رو نمی‌بریم — قبلاً دوبار دستکاریش کردیم (یه‌بار به Commands،
    یه‌بار به Default) و هر دفعه رفتار یکی از پلتفرم‌ها (موبایل/دسکتاپ) به‌طور غیرمنتظره
    عوض شد. با نکردن هیچ تنظیمی، تلگرام از رفتار طبیعی و پیش‌فرض خودش استفاده می‌کنه —
    که قرار بود از اولش همینه.
    """
    await app.bot.set_my_commands([
        ("start", "شروع و دیدن راهنمای کامل"),
        ("watch", "اضافه کردن ارز به لیست تحت‌نظر"),
        ("unwatch", "حذف ارز از لیست تحت‌نظر"),
        ("watchlist", "دیدن لیست ارزهای تحت‌نظر"),
        ("calculate", "محاسبه‌ی حجم پوزیشن مرحله‌به‌مرحله"),
        ("check", "بررسی معامله با کد (تک‌خطی)"),
        ("clearold", "پاک‌سازی تحلیل‌های قدیمی"),
        ("testnews", "تست فوری فید خبری (تشخیصی)"),
        ("techniques", "محاسبه بر اساس تکنیک‌های تحلیلی"),
        ("analyze", "تحلیل فوری یه ارز دلخواه"),
        ("glossary", "راهنمای اصطلاحات"),
        ("recent", "خبرهای مهم ۶ ساعت اخیر"),
        ("settings", "تنظیمات (تقویم، منطقه زمانی، واحد پول)"),
        ("cancel", "لغو عملیات در حال انجام"),
    ])



def main():
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN.startswith("اینجا_"):
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN تنظیم نشده. فایل tokens.env رو باز کن و مقدار واقعیش رو بذار."
        )
    if not TELEGRAM_CHAT_ID or TELEGRAM_CHAT_ID.startswith("اینجا_"):
        raise RuntimeError(
            "TELEGRAM_CHAT_ID تنظیم نشده. فایل tokens.env رو باز کن و مقدار واقعیش رو بذار."
        )

    init_db()
    for uid in AUTHORIZED_USER_IDS:
        seed_watchlist_if_empty(DEFAULT_WATCHED_COINS, uid)

    builder = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(setup_bot_commands)

    # اگه پروکسی Cloudflare Worker تنظیم شده باشه (برای وقتی دسترسی مستقیم به
    # api.telegram.org مسدوده)، همه‌ی درخواست‌های API و فایل از اون رد می‌شن.
    # اگه خالی باشه (پیش‌فرض)، ربات مستقیم و عادی به تلگرام وصل می‌شه.
    if CLOUDFLARE_WORKER_URL:
        builder = builder.base_url(f"{CLOUDFLARE_WORKER_URL}/bot").base_file_url(f"{CLOUDFLARE_WORKER_URL}/file/bot")
        print(f"[پروکسی] درخواست‌های تلگرام از Worker رد می‌شن: {CLOUDFLARE_WORKER_URL}")

    app = builder.build()

    # لایه‌ی محافظتی: قبل از هر چیز دیگه‌ای چک می‌کنه فرستنده مجازه یا نه
    # (group=-1 یعنی این handler با اولویت بالاتر از همه اجرا می‌شه)
    app.add_handler(MessageHandler(filters.ALL, check_authorization), group=-1)

    # دستورات ساده
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("check", handle_check_command))
    app.add_handler(CommandHandler("watchlist", watchlist_command))
    app.add_handler(MessageHandler(filters.Regex(r"^📋 واچ‌لیست$"), watchlist_command))
    app.add_handler(CommandHandler("testnews", testnews_command))
    app.add_handler(MessageHandler(filters.Regex(r"^🔍 تست فید$"), testnews_command))
    app.add_handler(CommandHandler("recent", recent_news_command))
    app.add_handler(MessageHandler(filters.Regex(r"^🕕 اخبار اخیر$"), recent_news_command))

    # منوی تنظیمات (تقویم، منطقه زمانی، واحد پول)
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(MessageHandler(filters.Regex(r"^⚙️ تنظیمات$"), settings_command))
    settings_conversation = ConversationHandler(
        entry_points=[CallbackQueryHandler(settings_callback, pattern=r"^settings:")],
        states={
            WAITING_CITY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_city_name)],
            WAITING_CITY_TZ: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_city_tz)],
            WAITING_TOMAN_RATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_toman_rate)],
        },
        fallbacks=[CommandHandler("cancel", cancel_settings)],
    )
    app.add_handler(settings_conversation)

    # دکمه‌ی 📌 پیگیری زیر پیام محاسبه‌ی معامله
    app.add_handler(CallbackQueryHandler(track_callback, pattern=r"^track:"))

    # منوی «محاسبه بر اساس تکنیک‌ها»
    app.add_handler(CommandHandler("techniques", techniques_menu_command))
    app.add_handler(MessageHandler(filters.Regex(r"^🧠 تکنیک‌ها$"), techniques_menu_command))
    technique_conversation = ConversationHandler(
        entry_points=[CallbackQueryHandler(technique_selected, pattern=r"^tech:")],
        states={
            WAITING_COIN_FOR_TECHNIQUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_coin_for_technique)],
        },
        fallbacks=[CommandHandler("cancel", cancel_technique)],
    )
    app.add_handler(technique_conversation)

    # دکمه‌ی «🔬 تحلیل ارز» — تحلیل فوری و مستقل از خبر
    standalone_analysis_conversation = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"^🔬 تحلیل ارز$"), start_standalone_analysis),
            CommandHandler("analyze", start_standalone_analysis),
        ],
        states={
            WAITING_COIN_FOR_ANALYSIS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_coin_for_analysis)],
        },
        fallbacks=[CommandHandler("cancel", cancel_standalone_analysis)],
    )
    app.add_handler(standalone_analysis_conversation)

    # راهنمای اصطلاحات
    app.add_handler(CommandHandler("glossary", glossary_command))
    app.add_handler(MessageHandler(filters.Regex(r"^📖 اصطلاحات$"), glossary_command))

    # مکالمه‌ی اضافه‌کردن ارز — /watch ADA مستقیم کار می‌کنه، /watch یا دکمه تنها می‌پرسه
    watch_conversation = ConversationHandler(
        entry_points=[
            CommandHandler("watch", watch_entry),
            MessageHandler(filters.Regex(r"^➕ افزودن ارز$"), watch_entry),
        ],
        states={
            WAITING_WATCH_SYMBOL: [MessageHandler(filters.TEXT & ~filters.COMMAND, watch_receive)],
        },
        fallbacks=[CommandHandler("cancel", cancel_watch)],
    )
    app.add_handler(watch_conversation)

    # مکالمه‌ی حذف ارز
    unwatch_conversation = ConversationHandler(
        entry_points=[
            CommandHandler("unwatch", unwatch_entry),
            MessageHandler(filters.Regex(r"^➖ حذف ارز$"), unwatch_entry),
        ],
        states={
            WAITING_UNWATCH_SYMBOL: [MessageHandler(filters.TEXT & ~filters.COMMAND, unwatch_receive)],
        },
        fallbacks=[CommandHandler("cancel", cancel_watch)],
    )
    app.add_handler(unwatch_conversation)

    # مکالمه‌ی پاک‌سازی تحلیل‌های قدیمی
    clearold_conversation = ConversationHandler(
        entry_points=[
            CommandHandler("clearold", clearold_entry),
            MessageHandler(filters.Regex(r"^🗑 پاک‌سازی$"), clearold_entry),
        ],
        states={
            WAITING_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, clearold_receive)],
        },
        fallbacks=[CommandHandler("cancel", cancel_clearold)],
    )
    app.add_handler(clearold_conversation)

    # مکالمه‌ی مرحله‌به‌مرحله‌ی محاسبه‌ی معامله (باید قبل از هندلر عمومی متن ثبت بشه)
    calc_conversation = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"^محاسبه\s+معامله$"), start_calc),
            MessageHandler(filters.Regex(r"^🧮 محاسبه معامله$"), start_calc),
            CommandHandler("calculate", start_calc),
            CallbackQueryHandler(start_calc_from_button, pattern=r"^calc:"),
        ],
        states={
            WAITING_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_code)],
            WAITING_CAPITAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_capital)],
            WAITING_RISK: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_risk)],
        },
        fallbacks=[CommandHandler("cancel", cancel_calc)],
    )
    app.add_handler(calc_conversation)

    # دکمه‌ی «🔥 میم‌کوین‌های داغ» — روشن/خاموش با یه دکمه
    app.add_handler(MessageHandler(filters.Regex(r"^🔥 میم‌کوین‌های داغ$"), meme_focus_toggle_handler))

    # پیام‌های متنی معمولی (فرمت تک‌خطی "بررسی معامله ...")
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # زمان‌بندی چک دوره‌ای اخبار (واکنشی، هر چند دقیقه)
    app.job_queue.run_repeating(
        check_news_job,
        interval=NEWS_CHECK_INTERVAL_MINUTES * 60,
        first=10,
    )

    # زمان‌بندی چک دوره‌ای لیستینگ‌های تازه‌ی Binance (میم‌کوین‌های تازه‌وارد و غیره)
    app.job_queue.run_repeating(
        check_new_listings_job,
        interval=NEW_LISTINGS_CHECK_INTERVAL_MINUTES * 60,
        first=20,
    )

    # زمان‌بندی چک دوره‌ای میم‌کوین‌های داغ (نوسان غیرعادی قیمت/حجم)
    app.job_queue.run_repeating(
        check_hot_meme_coins_job,
        interval=HOT_MEME_CHECK_INTERVAL_MINUTES * 60,
        first=30,
    )

    # زمان‌بندی خلاصه‌ی دوره‌ای (مستقل از خبر، ساعت‌های ثابت)
    tehran_tz = ZoneInfo(TIMEZONE)
    for hour in DAILY_DIGEST_HOURS:
        app.job_queue.run_daily(
            daily_digest_job,
            time=dt.time(hour=hour, minute=0, tzinfo=tehran_tz),
        )

    # پیگیری‌های معلق (که قبل از ری‌استارت ربات فعال شده بودن) رو دوباره زمان‌بندی کن
    reschedule_pending_tracks(app)

    print("ربات در حال اجراست...")
    app.run_polling()


if __name__ == "__main__":
    main()
