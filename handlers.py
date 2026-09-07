# -*- coding: utf-8 -*-
"""
پردازش پیام‌های ورودی از کاربر در تلگرام.
دو فرمت پشتیبانی می‌شه:
  1) بررسی معامله NWS-001 1000 2
  2) /check NWS-001 1000 2
"""

import re
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from db import get_analysis, get_user_settings
from risk import calculate_position_size
from indicators import rsi_short_tag, atr_short_tag, direction_label
from futures import long_short_short_tag
from formatting import format_money
from config import CHANNEL_ID
from news import _laddered_targets_block

PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
ENGLISH_DIGITS = "0123456789"


def normalize_digits(text):
    """تبدیل ارقام فارسی/عربی به انگلیسی تا پردازش عدد راحت باشه."""
    table = str.maketrans(PERSIAN_DIGITS + ARABIC_DIGITS, ENGLISH_DIGITS * 2)
    return text.translate(table)


# فرمت‌های قابل قبول: "بررسی معامله CODE CAPITAL RISK" یا "/check CODE CAPITAL RISK"
PATTERN = re.compile(
    r"(?:بررسی\s+معامله|/check)\s+([A-Za-z0-9\-]+)\s+([\d.]+)\s+([\d.]+)"
)


def build_risk_reply(code, analysis, capital, risk_percent, result, settings=None):
    """
    ساخت متن پاسخ نهایی — کامل، شامل هم اطلاعات تحلیل (ورود/خروج/استاپ)
    هم محاسبه‌ی ریسک بر پایه‌ی سرمایه‌ی کاربر. برچسب‌ها فارسی+انگلیسی کنار هم.
    مبالغ بر اساس تنظیمات کاربر (دلار یا تومان) نشون داده می‌شن.
    مشترک بین فرمت تک‌خطی و فرمت مکالمه‌ای.
    """
    if settings is None:
        settings = {"calendar": "gregorian", "timezone": "Asia/Tehran", "currency": "USD", "toman_rate": None}

    leverage = result["required_leverage"]
    if leverage is not None and leverage <= 1:
        leverage_line = "🔧 اهرم پیشنهادی (Suggested Leverage): نیازی نیست (حجم پوزیشن از سرمایه‌ت کمتره)"
    else:
        leverage_line = f"🔧 اهرم پیشنهادی (Suggested Leverage): {leverage}x"

    rsi = analysis.get("rsi")
    atr = analysis.get("atr")
    price = analysis.get("price")

    return (
        f"📊 تحلیل معامله {code} ({analysis['coin']})\n"
        f"{direction_label(analysis.get('direction', 'LONG'))}\n\n"
        f"📥 ورود (Entry): {price}\n"
        f"{_laddered_targets_block(analysis)}\n"
        f"🛑 حد ضرر (Stop Loss): {analysis.get('stop_loss')}{' 🧱 (بر پایه‌ی حمایت/مقاومت)' if analysis.get('sr_used_for_stop') else ''}\n"
        f"🧱 حمایت (Support): {analysis.get('support')} | مقاومت (Resistance): {analysis.get('resistance')}\n"
        f"⚖️ نسبت ریسک به ریوارد (Risk:Reward): 1:{analysis.get('risk_reward')}\n"
        f"⏱️ افق زمانی (Time Horizon): {analysis.get('time_horizon')}\n"
        f"📈 RSI: {rsi} ({rsi_short_tag(rsi)}) | 📉 ATR: {atr} ({atr_short_tag(atr, price)}, تایم‌فریم: {analysis.get('atr_interval_label')})\n"
        f"📊 لانگ/شورت: {analysis.get('ls_ratio')} ({long_short_short_tag(analysis.get('ls_ratio'))}) | "
        f"حجم: {analysis.get('volume_ratio')}× میانگین | MA۵۰: {analysis.get('ma_trend_percent')}٪\n\n"
        f"💰 محاسبه بر اساس سرمایه‌ی تو (Capital: {format_money(capital, settings)}, Risk: {risk_percent}%):\n"
        f"• حداکثر مبلغ در ریسک (Risk Amount): {format_money(result['risk_amount'], settings)}\n"
        f"• فاصله‌ی استاپ تا ورود (Stop Distance): {result['stop_distance_percent']}%\n"
        f"• حجم پوزیشن پیشنهادی (Position Size): {format_money(result['position_size'], settings)}\n"
        f"• کارمزد تخمینی رفت‌وبرگشت (⚠️ تقریبی، صرافی خودتو چک کن): {format_money(result.get('estimated_fee'), settings)}\n"
        f"{leverage_line}\n\n"
        f"این اهرم مستقیماً از فرمول (حجم پوزیشن ÷ سرمایه‌ی خودت) به‌دست اومده — "
        f"نه یه پیشنهاد دلبخواهی. تصمیم نهایی و مسئولیت هر معامله‌ای همیشه با خودته.\n"
        f"⚠️ این یه محاسبه‌ی ریاضی بر پایه‌ی فرمول رایج مدیریت ریسکه (Risk Management Formula)، "
        f"نه توصیه‌ی مالی شخصی‌سازی‌شده.\n\n"
        f"🔗 نکته‌ی ریسک همبستگی: این محاسبه فرض می‌کنه این تنها معامله‌ی بازته. اگه هم‌زمان "
        f"رو چند ارز همبسته (مثلاً BTC و ETH با هم) هم پوزیشن باز داری، ریسک واقعی‌ت جمع همه‌شونه، "
        f"نه هرکدوم جدا — با درصد ریسک کمتر برای هرکدوم جبرانش کن."
    )


async def _send_risk_reply(update: Update, code, capital, risk_percent):
    analysis = get_analysis(code)
    if analysis is None:
        await update.message.reply_text(f"کد {code} پیدا نشد. مطمئن شو کد رو درست کپی کردی.")
        return

    result = calculate_position_size(
        capital=capital,
        risk_percent=risk_percent,
        entry_price=analysis["price"],
        stop_loss_price=analysis["stop_loss"],
    )

    if result is None:
        await update.message.reply_text("محاسبه ممکن نشد — داده‌ی استاپ‌لاس این تحلیل ناقصه.")
        return

    settings = get_user_settings(update.effective_user.id)
    reply_text = build_risk_reply(code, analysis, capital, risk_percent, result, settings)

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("📌 پیگیری", callback_data=f"track:{code}")]])
    await update.message.reply_text(reply_text, reply_markup=keyboard)

    # علاوه بر خود چت، اگه کانال تنظیم شده، اونجا هم بفرست (برای مرور راحت‌تر بعداً)
    if CHANNEL_ID:
        try:
            await update.get_bot().send_message(chat_id=CHANNEL_ID, text=reply_text)
        except Exception as e:
            print(f"[خطا در ارسال به کانال] {e}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_text = update.message.text or ""
    text = normalize_digits(raw_text)

    match = PATTERN.search(text)
    if not match:
        await update.message.reply_text(
            "فرمت پیام رو متوجه نشدم.\n"
            "مثال درست:\nبررسی معامله NWS-001 1000 2\n"
            "یا: /check NWS-001 1000 2\n\n"
            "یا اگه می‌خوای مرحله‌به‌مرحله جواب بدی، بنویس: محاسبه معامله"
        )
        return

    code, capital_str, risk_str = match.groups()
    capital = float(capital_str)
    risk_percent = float(risk_str)

    await _send_risk_reply(update, code, capital, risk_percent)


async def handle_check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پشتیبانی از فرمت /check به‌عنوان دستور جدا (علاوه بر تشخیص متنی بالا)."""
    await handle_message(update, context)
