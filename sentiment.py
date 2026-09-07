# -*- coding: utf-8 -*-
"""
گرفتن شاخص ترس و طمع بازار (Fear & Greed Index) از Alternative.me
یه عدد ۰ تا ۱۰۰ که از ترکیب نوسان قیمت، حجم، شبکه‌های اجتماعی،
نظرسنجی، دامیننس بیت‌کوین و گوگل ترندز محاسبه می‌شه. رایگان و بدون نیاز به کلید.
"""

import requests

FEAR_GREED_URL = "https://api.alternative.me/fng/?limit=1"


def get_fear_greed_index():
    """برمی‌گردونه: (عدد ۰ تا ۱۰۰, برچسب فارسی) یا (None, None) در صورت خطا."""
    try:
        resp = requests.get(FEAR_GREED_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()["data"][0]
        value = int(data["value"])
        return value, _classify(value)
    except Exception as e:
        print(f"[خطا در گرفتن Fear & Greed] {e}")
        return None, None


def _classify(value):
    if value <= 25:
        return "ترس شدید (Extreme Fear)"
    elif value <= 45:
        return "ترس (Fear)"
    elif value <= 55:
        return "خنثی (Neutral)"
    elif value <= 75:
        return "طمع (Greed)"
    else:
        return "طمع شدید (Extreme Greed)"


def interpret_fear_greed(value, label):
    if value is None:
        return "داده کافی برای محاسبه نیست"
    return (
        f"{value}/100 — {label}. این شاخص حس کلی بازار رو نشون می‌ده "
        f"(ترکیبی از نوسان قیمت، حجم معاملات، شبکه‌های اجتماعی و گوگل ترندز)، "
        f"نه یه ارز خاص."
    )
