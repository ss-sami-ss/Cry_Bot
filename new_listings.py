# -*- coding: utf-8 -*-
"""
تشخیص لیستینگ‌های تازه رو Binance (شامل میم‌کوین‌های تازه‌وارد که ممکنه بترکن).

⚠️ محدودیت مهم: نمی‌تونیم مطمئن باشیم یه نماد جدید واقعاً «میم‌کوین»ه یا یه پروژه‌ی
جدی — این نیاز به دیتای دسته‌بندی داره که رایگان در دسترس نیست. برای همین، هر
جفت‌ارز USDT تازه‌لیست‌شده رو گزارش می‌کنیم (که در عمل، اکثر لیستینگ‌های ناگهانی
Binance همین میم‌کوین‌ها و پروژه‌های پرهیجانن)، ولی تشخیص قطعی «میم‌کوینه یا نه»
با خودِ کاربره.
"""

import requests

from db import get_known_symbols, add_known_symbols, known_symbols_count

BINANCE_EXCHANGE_INFO_URL = "https://api.binance.com/api/v3/exchangeInfo"


def _fetch_all_usdt_symbols():
    """همه‌ی جفت‌ارزهای USDT که الان رو Binance در حال معامله‌ان."""
    try:
        resp = requests.get(BINANCE_EXCHANGE_INFO_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        symbols = [
            s["symbol"] for s in data.get("symbols", [])
            if s.get("quoteAsset") == "USDT" and s.get("status") == "TRADING"
        ]
        return symbols
    except Exception as e:
        print(f"[خطا در گرفتن لیست نمادهای Binance] {e}")
        return []


def check_new_listings():
    """
    لیست نمادهای الان رو با چیزی که قبلاً می‌شناختیم مقایسه می‌کنه.
    دفعه‌ی اول (وقتی دیتابیس خالیه)، فقط لیست رو پر می‌کنه و هیچی گزارش نمی‌ده —
    چون وگرنه صدها نماد قدیمی رو به‌اشتباه «جدید» گزارش می‌داد.

    برمی‌گردونه: لیست نمادهای واقعاً تازه‌لیست‌شده (می‌تونه خالی باشه).
    """
    current_symbols = _fetch_all_usdt_symbols()
    if not current_symbols:
        return []

    is_first_run = known_symbols_count() == 0

    known = get_known_symbols()
    new_symbols = [s for s in current_symbols if s not in known]

    add_known_symbols(current_symbols)

    if is_first_run:
        return []

    return sorted(new_symbols)


def build_new_listing_message(symbol):
    coin = symbol.replace("USDT", "")
    return (
        f"🆕 لیستینگ تازه رو Binance: {coin}\n\n"
        f"این نماد تا الان تو دیتابیس ربات نبود — یا کوینِ کاملاً جدیده، یا تازه رو "
        f"Binance لیست شده. این می‌تونه یه میم‌کوین پرهیجان باشه یا یه پروژه‌ی جدی —\n"
        f"⚠️ خودت بررسی کن چیه، چون هنوز داده‌ی کافی (تاریخچه‌ی قیمت) برای تحلیل "
        f"تکنیکال کامل نداریم.\n\n"
        f"می‌تونی با /analyze یا دکمه‌ی 🔬 تحلیل ارز، اسم {coin} رو بزنی و ببینی "
        f"داده‌ی کافی برای تحلیل جمع شده یا نه."
    )
