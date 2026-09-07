# -*- coding: utf-8 -*-
"""
اسکن میم‌کوین‌های «داغ» — چه از لیست شناخته‌شده‌ی میم‌کوین‌ها، چه از لیستینگ‌های
تازه‌ی چند روز اخیر — که نوسان قیمت/حجم غیرعادی (احتمال «ترکیدن») داشته باشن.

⚠️ محدودیت: هیچ منبع رایگانی نداریم که رسماً «میم‌کوین» رو دسته‌بندی کنه، پس یه
لیست دستی از میم‌کوین‌های شناخته‌شده نگه می‌داریم (قابل‌گسترش) + لیستینگ‌های
تازه‌ی چند روز اخیر (که اغلب همین‌جور کوین‌هان).
"""

import requests

from db import get_recently_known_symbols, can_send_hot_alert, mark_hot_alert_sent

BINANCE_TICKER_24H_URL = "https://api.binance.com/api/v3/ticker/24hr"

# لیست دستی میم‌کوین‌های شناخته‌شده — هروقت خواستی می‌شه بهش اضافه کرد
KNOWN_MEME_COINS = [
    "DOGE", "SHIB", "PEPE", "FLOKI", "BONK", "WIF", "MEME", "BABYDOGE",
    "MYRO", "POPCAT", "BRETT", "TURBO", "WOJAK", "LADYS", "MOG", "NEIRO",
    "PNUT", "GOAT", "ACT", "CHILLGUY", "MEW", "BOME", "SLERF",
]

HOT_PRICE_CHANGE_THRESHOLD = 15.0  # درصد تغییر قیمت ۲۴ ساعته که «داغ» حساب بشه
HOT_MIN_QUOTE_VOLUME = 500_000  # حداقل حجم معاملاتی (به دلار) که فیک/بی‌نقدینگی نباشه


def _fetch_all_tickers_24h():
    """آمار ۲۴ساعته‌ی همه‌ی جفت‌ارزها رو با یه درخواست می‌گیره (کارآمد، نه یکی‌یکی)."""
    try:
        resp = requests.get(BINANCE_TICKER_24H_URL, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[خطا در گرفتن آمار ۲۴ساعته] {e}")
        return []


def scan_hot_meme_coins():
    """
    برمی‌گردونه: لیست دیکشنری‌های {symbol, price_change_pct, quote_volume}
    برای میم‌کوین‌هایی (شناخته‌شده + تازه‌لیست‌شده) که همین الان «داغ»ان و اخیراً
    هشدارشون فرستاده نشده (cooldown ۶ ساعته).
    """
    candidates = set(f"{c}USDT" for c in KNOWN_MEME_COINS)
    candidates.update(get_recently_known_symbols(days=3))

    all_tickers = _fetch_all_tickers_24h()
    if not all_tickers:
        return []

    ticker_map = {t["symbol"]: t for t in all_tickers if isinstance(t, dict) and "symbol" in t}

    hot = []
    for symbol in candidates:
        ticker = ticker_map.get(symbol)
        if not ticker:
            continue
        try:
            price_change_pct = float(ticker.get("priceChangePercent", 0))
            quote_volume = float(ticker.get("quoteVolume", 0))
        except (TypeError, ValueError):
            continue

        if quote_volume < HOT_MIN_QUOTE_VOLUME:
            continue
        if abs(price_change_pct) < HOT_PRICE_CHANGE_THRESHOLD:
            continue
        if not can_send_hot_alert(symbol):
            continue

        hot.append({
            "symbol": symbol,
            "price_change_pct": round(price_change_pct, 2),
            "quote_volume": round(quote_volume, 0),
        })
        mark_hot_alert_sent(symbol)

    return sorted(hot, key=lambda x: abs(x["price_change_pct"]), reverse=True)


def build_hot_meme_message(hot_item):
    coin = hot_item["symbol"].replace("USDT", "")
    direction = "🚀 صعود" if hot_item["price_change_pct"] > 0 else "📉 سقوط"
    return (
        f"🔥 میم‌کوین داغ: {coin}\n\n"
        f"{direction} {abs(hot_item['price_change_pct'])}٪ تو ۲۴ ساعت اخیر\n"
        f"💰 حجم معاملات ۲۴ساعته: ~${hot_item['quote_volume']:,.0f}\n\n"
        f"⚠️ نوسان شدید = ریسک بالا. برای تحلیل کامل، از /analyze یا دکمه‌ی "
        f"🔬 تحلیل ارز استفاده کن."
    )
