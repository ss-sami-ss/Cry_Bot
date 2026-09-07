# -*- coding: utf-8 -*-
"""
دکمه‌ی «🔬 تحلیل ارز» — تحلیل فوری و مستقل از خبر برای هر ارزی که بخوای،
همون لحظه‌ای که خودت می‌خوای، نه فقط وقتی خبری منتشر بشه.
"""

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler

from news import compute_standalone_analysis, render_standalone_text
from db import get_user_settings

WAITING_COIN_FOR_ANALYSIS = 200


async def start_standalone_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("کدوم ارز رو می‌خوای تحلیل کنم؟ (مثلاً BTC، XRP، ADA):")
    return WAITING_COIN_FOR_ANALYSIS


async def receive_coin_for_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    coin = update.message.text.strip().upper()
    binance_symbol = f"{coin}USDT"

    await update.message.reply_text(f"در حال تحلیل {coin}، چند ثانیه صبر کن...")

    data = compute_standalone_analysis(coin, binance_symbol)
    if data is None:
        await update.message.reply_text(
            f"نشد {coin} رو تحلیل کنم — نماد {binance_symbol} روی Binance پیدا نشد یا داده کافی نداشت. "
            f"مطمئن شو اسم ارز درسته."
        )
        return ConversationHandler.END

    settings = get_user_settings(update.effective_user.id)
    text = render_standalone_text(data, settings)
    code = data["code"]

    if code:
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🧮 محاسبه معامله", callback_data=f"calc:{code}")]])
        await update.message.reply_text(text, reply_markup=keyboard)
    else:
        await update.message.reply_text(text)

    return ConversationHandler.END


async def cancel_standalone_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لغو شد.")
    return ConversationHandler.END
