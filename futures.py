# -*- coding: utf-8 -*-
"""
داده‌های بازار فیوچرز از Binance — رایگان، بدون نیاز به کلید API.
این دو تا شاخص نشون می‌دن معامله‌گرهای اهرم‌دار چقدر یک‌طرفه (لانگ یا شورت) شدن،
که معمولاً پیش‌نشونه‌ی ریسک اصلاح شدید قیمته (دقیقاً همون چیزی که در ریزش XRP دیدیم).
"""

import requests

FUNDING_RATE_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
OPEN_INTEREST_HIST_URL = "https://fapi.binance.com/futures/data/openInterestHist"
LONG_SHORT_RATIO_URL = "https://fapi.binance.com/futures/data/globalLongShortAccountRatio"


def get_funding_rate(symbol):
    """نرخ فاندینگ فعلی (به‌صورت درصد). مثبت بزرگ = بازار پر از لانگ، منفی بزرگ = پر از شورت."""
    try:
        resp = requests.get(FUNDING_RATE_URL, params={"symbol": symbol}, timeout=10)
        resp.raise_for_status()
        rate = float(resp.json()["lastFundingRate"])
        return round(rate * 100, 4)  # تبدیل به درصد
    except Exception as e:
        print(f"[خطا در گرفتن فاندینگ ریت] {e}")
        return None


def get_open_interest_change(symbol, period="1h", limit=24):
    """درصد تغییر حجم پوزیشن‌های باز فیوچرز در بازه‌ی اخیر."""
    try:
        resp = requests.get(
            OPEN_INTEREST_HIST_URL,
            params={"symbol": symbol, "period": period, "limit": limit},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if len(data) < 2:
            return None
        old_oi = float(data[0]["sumOpenInterest"])
        new_oi = float(data[-1]["sumOpenInterest"])
        if old_oi == 0:
            return None
        return round((new_oi - old_oi) / old_oi * 100, 2)
    except Exception as e:
        print(f"[خطا در گرفتن تغییرات پوزیشن‌های باز] {e}")
        return None


def get_long_short_ratio(symbol, period="1h"):
    """
    نسبت تعداد حساب‌های لانگ به شورت (نه حجم، تعداد حساب). عدد بالای ۱ یعنی
    اکثریت حساب‌ها لانگ‌ان، زیر ۱ یعنی اکثریت شورت‌ان.
    """
    try:
        resp = requests.get(
            LONG_SHORT_RATIO_URL,
            params={"symbol": symbol, "period": period, "limit": 1},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return None
        return round(float(data[-1]["longShortRatio"]), 3)
    except Exception as e:
        print(f"[خطا در گرفتن نسبت لانگ/شورت] {e}")
        return None


def interpret_long_short_ratio(ratio):
    if ratio is None:
        return "داده کافی برای محاسبه نیست"

    if ratio >= 1.5:
        return f"{ratio} — اکثریت حساب‌ها لانگ‌ان؛ بازار یک‌طرفه به سمت خرید شده، ریسک اصلاح بالاتر رفته"
    elif ratio <= 0.67:
        return f"{ratio} — اکثریت حساب‌ها شورت‌ان؛ بازار یک‌طرفه به سمت فروش شده، ریسک بازگشت بالاتر رفته"
    else:
        return f"{ratio} — نسبت حساب‌های لانگ به شورت در محدوده‌ی متعادل"


def long_short_short_tag(ratio):
    """نسخه‌ی کوتاه برای پیام فشرده."""
    if ratio is None:
        return ""
    if ratio >= 1.5:
        return "اکثریت لانگ"
    elif ratio <= 0.67:
        return "اکثریت شورت"
    return "متعادل"


def interpret_funding_rate(rate_percent):
    if rate_percent is None:
        return "داده کافی برای محاسبه نیست"

    if rate_percent >= 0.05:
        return f"{rate_percent}٪ — فاندینگ مثبت بالا؛ بازار پر از پوزیشن‌های لانگ اهرم‌دار شده، ریسک اصلاح ناگهانی (Long Squeeze) بالاتر رفته"
    elif rate_percent <= -0.05:
        return f"{rate_percent}٪ — فاندینگ منفی بالا؛ بازار پر از پوزیشن‌های شورت اهرم‌دار شده، ریسک جهش ناگهانی (Short Squeeze) بالاتر رفته"
    else:
        return f"{rate_percent}٪ — در محدوده‌ی عادی، بازار به‌شکل خاصی یک‌طرفه (لانگ یا شورت) نشده"


def funding_short_tag(rate_percent):
    """نسخه‌ی کوتاه برای پیام فشرده."""
    if rate_percent is None:
        return ""
    if rate_percent >= 0.05:
        return "ازدحام لانگ"
    elif rate_percent <= -0.05:
        return "ازدحام شورت"
    return "عادی"


def interpret_open_interest_change(change_percent, period_hours=24):
    if change_percent is None:
        return "داده کافی برای محاسبه نیست"

    direction = "افزایش" if change_percent > 0 else "کاهش"
    note = ""
    if abs(change_percent) >= 10:
        note = " — تغییر بزرگیه؛ یعنی حجم قابل‌توجهی پوزیشن اهرم‌دار جدید وارد یا خارج شده، که آسیب‌پذیری بازار به نوسان رو بالا می‌بره"

    return f"{change_percent}٪ {direction} در {period_hours} ساعت اخیر{note}"
