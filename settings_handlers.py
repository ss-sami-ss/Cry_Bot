# -*- coding: utf-8 -*-
"""
منوی تنظیمات شخصی هر کاربر: تقویم (شمسی/میلادی)، منطقه زمانی، واحد پول (دلار/تومان).
با دکمه‌های inline کار می‌کنه (نه تایپ دستی).
"""

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler

from db import get_user_settings, update_user_settings, add_custom_timezone, get_all_timezones
from zoneinfo import ZoneInfo

WAITING_CITY_NAME, WAITING_CITY_TZ, WAITING_TOMAN_RATE = range(3)


def _settings_keyboard(settings):
    calendar_label = "📅 تقویم: شمسی" if settings["calendar"] == "shamsi" else "📅 تقویم: میلادی"
    currency_label = "💵 واحد پول: تومان" if settings["currency"] == "TOMAN" else "💵 واحد پول: دلار"
    tz_label = f"🌍 منطقه زمانی: {settings['timezone']}"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(calendar_label + " (تغییر بده)", callback_data="settings:toggle_calendar")],
        [InlineKeyboardButton(currency_label + " (تغییر بده)", callback_data="settings:toggle_currency")],
        [InlineKeyboardButton(tz_label + " (تغییر بده)", callback_data="settings:change_tz")],
        [InlineKeyboardButton("➕ افزودن شهر/منطقه‌ی جدید", callback_data="settings:add_city")],
        [InlineKeyboardButton("✏️ تنظیم نرخ دلار به تومان", callback_data="settings:set_rate")],
    ])


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    settings = get_user_settings(user_id)
    await update.message.reply_text(
        "⚙️ تنظیمات شخصی تو — روی هرکدوم بزن که عوضش کنی:",
        reply_markup=_settings_keyboard(settings),
    )


async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    action = query.data.split(":", 1)[1]

    if action == "toggle_calendar":
        current = get_user_settings(user_id)
        new_val = "gregorian" if current["calendar"] == "shamsi" else "shamsi"
        update_user_settings(user_id, calendar=new_val)
        settings = get_user_settings(user_id)
        await query.edit_message_text("⚙️ تنظیمات شخصی تو — روی هرکدوم بزن که عوضش کنی:", reply_markup=_settings_keyboard(settings))
        return ConversationHandler.END

    if action == "toggle_currency":
        current = get_user_settings(user_id)
        new_val = "USD" if current["currency"] == "TOMAN" else "TOMAN"
        update_user_settings(user_id, currency=new_val)
        settings = get_user_settings(user_id)
        await query.edit_message_text("⚙️ تنظیمات شخصی تو — روی هرکدوم بزن که عوضش کنی:", reply_markup=_settings_keyboard(settings))
        return ConversationHandler.END

    if action == "change_tz":
        timezones = get_all_timezones()
        buttons = [
            [InlineKeyboardButton(city, callback_data=f"settings:pick_tz:{city}")]
            for city in timezones
        ]
        await query.edit_message_text("کدوم شهر/منطقه رو می‌خوای انتخاب کنی؟", reply_markup=InlineKeyboardMarkup(buttons))
        return ConversationHandler.END

    if action.startswith("pick_tz:"):
        city = action.split(":", 1)[1]
        timezones = get_all_timezones()
        tz_name = timezones.get(city, "Asia/Tehran")
        update_user_settings(user_id, timezone=tz_name)
        settings = get_user_settings(user_id)
        await query.edit_message_text(f"✅ منطقه زمانی روی «{city}» تنظیم شد.", reply_markup=_settings_keyboard(settings))
        return ConversationHandler.END

    if action == "add_city":
        await query.edit_message_text("اسم شهر/منطقه رو بنویس (مثلاً «برلین»):")
        return WAITING_CITY_NAME

    if action == "set_rate":
        await query.edit_message_text("نرخ فعلی دلار به تومان رو بنویس (فقط عدد، مثلاً 90000):")
        return WAITING_TOMAN_RATE

    return ConversationHandler.END


async def receive_city_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_city_name"] = update.message.text.strip()
    await update.message.reply_text(
        "حالا شناسه‌ی IANA تایم‌زون اون شهر رو بنویس (مثلاً برای برلین: Europe/Berlin).\n"
        "اگه نمی‌دونی، تو گوگل بنویس: IANA timezone [اسم شهر]"
    )
    return WAITING_CITY_TZ


async def receive_city_tz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tz_name = update.message.text.strip()
    city_name = context.user_data.get("new_city_name", "شهر جدید")

    try:
        ZoneInfo(tz_name)  # اعتبارسنجی
    except Exception:
        await update.message.reply_text(
            f"«{tz_name}» یه شناسه‌ی معتبر IANA نیست. دوباره امتحان کن (مثلاً Europe/Berlin) یا /cancel بزن."
        )
        return WAITING_CITY_TZ

    add_custom_timezone(city_name, tz_name)
    user_id = update.effective_user.id
    update_user_settings(user_id, timezone=tz_name)
    settings = get_user_settings(user_id)
    await update.message.reply_text(
        f"✅ «{city_name}» اضافه شد و منطقه زمانی روش تنظیم شد.",
        reply_markup=_settings_keyboard(settings),
    )
    context.user_data.clear()
    return ConversationHandler.END


async def receive_toman_rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(",", "")
    try:
        rate = float(text)
    except ValueError:
        await update.message.reply_text("لطفاً فقط عدد بفرست (مثلاً 90000):")
        return WAITING_TOMAN_RATE

    user_id = update.effective_user.id
    update_user_settings(user_id, toman_rate=rate)
    settings = get_user_settings(user_id)
    await update.message.reply_text(
        f"✅ نرخ روی {rate:,.0f} تومان به ازای هر دلار تنظیم شد.",
        reply_markup=_settings_keyboard(settings),
    )
    return ConversationHandler.END


async def cancel_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("لغو شد.")
    return ConversationHandler.END
