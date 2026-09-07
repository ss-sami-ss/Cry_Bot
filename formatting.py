# -*- coding: utf-8 -*-
"""
فرمت‌بندی تاریخ/ساعت و واحد پول، بر اساس تنظیمات شخصی هر کاربر
(تقویم شمسی یا میلادی، منطقه زمانی، دلار یا تومان).
"""

from datetime import datetime
from zoneinfo import ZoneInfo

_WEEKDAYS_FA = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]


def format_datetime(dt_utc: datetime, settings: dict) -> str:
    """
    dt_utc: یه datetime با تایم‌زون UTC (یا هر تایم‌زون‌دار دیگه‌ای)
    settings: دیکشنری تنظیمات کاربر (از db.get_user_settings)
    """
    tz_name = settings.get("timezone") or "Asia/Tehran"
    try:
        local_dt = dt_utc.astimezone(ZoneInfo(tz_name))
    except Exception:
        local_dt = dt_utc.astimezone(ZoneInfo("Asia/Tehran"))
        tz_name = "Asia/Tehran"

    weekday_name = _WEEKDAYS_FA[local_dt.weekday()]
    tz_label = tz_name.split("/")[-1].replace("_", " ")

    if settings.get("calendar") == "shamsi":
        try:
            import jdatetime
            j = jdatetime.datetime.fromgregorian(datetime=local_dt)
            date_str = j.strftime("%Y-%m-%d %H:%M")
        except Exception:
            date_str = local_dt.strftime("%Y-%m-%d %H:%M") + " (شمسی در دسترس نبود)"
    else:
        date_str = local_dt.strftime("%Y-%m-%d %H:%M")

    return f"{weekday_name} {date_str} (به وقت {tz_label})"


def format_money(usd_amount, settings: dict) -> str:
    """مبلغ دلاری رو بر اساس تنظیمات کاربر، دلار یا تومان نشون می‌ده."""
    if usd_amount is None:
        return "-"

    if settings.get("currency") == "TOMAN":
        rate = settings.get("toman_rate")
        if rate:
            toman = usd_amount * rate
            return f"{toman:,.0f} تومان (≈{usd_amount}$)"
        else:
            return f"{usd_amount}$ (نرخ تومان تنظیم نشده — از /settings تنظیم کن)"

    return f"{usd_amount}$"
