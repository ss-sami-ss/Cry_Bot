# -*- coding: utf-8 -*-
"""
تنظیمات مرکزی ربات
همه‌ی مقادیر حساس (توکن‌ها) از فایل tokens.env خونده می‌شن (نه این‌که مستقیم اینجا نوشته بشن).
این روش مستقل از ویندوز/Batch/انکودینگ عمل می‌کنه — خود پایتون مستقیم فایل رو می‌خونه.
"""

import os
from dotenv import load_dotenv

# فایل tokens.env رو از همون پوشه‌ای که این فایل توشه می‌خونه
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tokens.env")
load_dotenv(_env_path)

# --- تلگرام ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# --- پروکسی Cloudflare Worker (اختیاری) — برای وقتی دسترسی مستقیم به
# api.telegram.org مسدوده. اگه خالی بمونه، ربات مستقیم و عادی به تلگرام وصل می‌شه؛
# اگه پر بشه، همه‌ی درخواست‌ها (پیام، فایل) از این Worker رد می‌شن.
CLOUDFLARE_WORKER_URL = os.environ.get("CLOUDFLARE_WORKER_URL", "").rstrip("/")

# --- کاربرهای مجاز به استفاده از ربات (پرایوت‌سازی) ---
# چند تا آیدی عددی، با کاما جدا (مثلاً "123456789,987654321")
# اگه خالی بمونه، به‌صورت پیش‌فرض فقط همون TELEGRAM_CHAT_ID مجازه.
_raw_allowed = os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "")
if _raw_allowed.strip():
    AUTHORIZED_USER_IDS = {int(x.strip()) for x in _raw_allowed.split(",") if x.strip().isdigit()}
elif TELEGRAM_CHAT_ID.strip().lstrip("-").isdigit():
    AUTHORIZED_USER_IDS = {int(TELEGRAM_CHAT_ID)}
else:
    # یعنی TELEGRAM_CHAT_ID هنوز تنظیم نشده (یا مقدار غیرعددیه) — هیچ‌کس مجاز نیست
    AUTHORIZED_USER_IDS = set()

# --- CoinStats (فید خبری — جایگزین CryptoPanic که دیگه پلن رایگان نداره) ---
# ثبت‌نام رایگان: https://openapi.coinstats.app (۲۰,۰۰۰ کردیت رایگان در ماه)
COINSTATS_API_KEY = os.environ.get("COINSTATS_API_KEY", "")

# --- ارزهای پیش‌فرض که بار اول (فقط یه‌بار) به واچ‌لیست اضافه می‌شن ---
# بعد از این، واچ‌لیست پویاست و با دستورات تلگرامی /watch و /unwatch مدیریت می‌شه
DEFAULT_WATCHED_COINS = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "XRP": "XRPUSDT",
    "SOL": "SOLUSDT",
}

# --- هر چند دقیقه فید خبری چک بشه ---
NEWS_CHECK_INTERVAL_MINUTES = 10
NEW_LISTINGS_CHECK_INTERVAL_MINUTES = 30  # لیستینگ‌های جدید اونقدر مکرر نیستن که هر ۱۰ دقیقه چک بشه
HOT_MEME_CHECK_INTERVAL_MINUTES = 15  # نوسان‌های داغ سریع‌تر تغییر می‌کنن، پس مکررتر چک می‌شن

# --- کلمات کلیدی که تشخیص «خبر مهم» رو تعیین می‌کنن، در news.py لیست شدن ---

# --- ساعت‌های ارسال خلاصه‌ی دوره‌ای (به وقت تهران، فرمت 24 ساعته) ---
DAILY_DIGEST_HOURS = [9, 21]

# --- مسیر دیتابیس محلی (برای ذخیره‌ی تحلیل‌ها با کدشون) ---
DB_PATH = os.path.join(os.path.dirname(__file__), "analyses.db")

# --- تنظیمات اندیکاتورهای فنی ---
RSI_PERIOD = 14
ATR_PERIOD = 14
KLINES_INTERVAL = "1h"     # تایم‌فریم کندل‌ها برای محاسبه
KLINES_LOOKBACK = 100      # چند کندل برای محاسبه بگیریم
SUPPORT_RESISTANCE_LOOKBACK = 50  # چند کندل اخیر برای پیدا کردن سقف/کف

# --- تایم‌زون برای نمایش تاریخ/ساعت خبرها ---
TIMEZONE = "Asia/Tehran"

# --- کانال جداگانه برای ارسال پیشنهادها و نتیجه‌ی پیگیری (اختیاری) ---
# اگه پر باشه، علاوه بر خود چت، به این کانال هم فرستاده می‌شه (ربات باید ادمین کانال باشه)
CHANNEL_ID = os.environ.get("CHANNEL_ID", "")

# --- کارمزد تخمینی معامله (٪) — تخمین محافظه‌کارانه‌ی رفت‌وبرگشت (ورود+خروج) رو
# Binance Futures (Taker ~۰.۰۵٪ هر طرف). چون هدف‌های پله‌ای یعنی چند بار خروج
# (تا ۳ تا)، یه‌کم بیشتر از یه معامله‌ی ساده در نظر گرفته شده. صرافی/حساب خودت
# ممکنه فرق کنه — اگه دقیق می‌دونی، همین‌جا عوضش کن.
ESTIMATED_ROUNDTRIP_FEE_PERCENT = 0.15
