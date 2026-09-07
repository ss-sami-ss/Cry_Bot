# -*- coding: utf-8 -*-
"""
محاسبه‌ی حجم پوزیشن بر پایه‌ی فرمول استاندارد مدیریت ریسک.
ورودی این ماژول همیشه از خود کاربر میاد (سرمایه و درصد ریسک) —
این ماژول فقط فرمول ریاضی رایج رو روی عددهای خود کاربر اجرا می‌کنه،
هیچ عددی از پیش‌فرض یا حدسی درش نیست.
"""

from config import ESTIMATED_ROUNDTRIP_FEE_PERCENT


def calculate_position_size(capital, risk_percent, entry_price, stop_loss_price):
    """
    فرمول استاندارد مدیریت ریسک:
      مبلغ در ریسک = سرمایه × (درصد ریسک / 100)
      فاصله‌ی استاپ (درصدی) = |قیمت ورود - استاپ| / قیمت ورود
      حجم پوزیشن = مبلغ در ریسک / فاصله‌ی استاپ (درصدی)

    مبلغ کارمزد تخمینی هم جدا حساب می‌شه (روی حجم پوزیشن، نه سرمایه) —
    چون قبلاً هیچ‌جای محاسبات در نظر گرفته نمی‌شد و می‌تونست سود واقعی رو
    گمراه‌کننده نشون بده.
    """
    if entry_price == 0 or stop_loss_price is None:
        return None

    risk_amount = capital * (risk_percent / 100)
    stop_distance_percent = abs(entry_price - stop_loss_price) / entry_price

    if stop_distance_percent == 0:
        return None

    position_size = risk_amount / stop_distance_percent

    # اهرم مورد نیاز = حجم پوزیشن ÷ کل سرمایه
    # اگه حجم پوزیشن از کل سرمایه کمتر باشه، اصلاً اهرمی لازم نیست (یعنی مقدار ۱ یا کمتر)
    required_leverage = round(position_size / capital, 2) if capital else None

    estimated_fee = round(position_size * (ESTIMATED_ROUNDTRIP_FEE_PERCENT / 100), 2)

    return {
        "risk_amount": round(risk_amount, 2),
        "stop_distance_percent": round(stop_distance_percent * 100, 2),
        "position_size": round(position_size, 2),
        "required_leverage": required_leverage,
        "estimated_fee": estimated_fee,
    }
