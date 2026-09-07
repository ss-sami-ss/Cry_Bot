# -*- coding: utf-8 -*-
"""
منوی «محاسبه بر اساس تکنیک‌ها»:
  ۱) کاربر از کیبورد دکمه‌ی «🧠 تکنیک‌ها» رو می‌زنه
  ۲) یه منوی inline با لیست تکنیک‌ها باز می‌شه
  ۳) کاربر یکی رو انتخاب می‌کنه
  ۴) ربات می‌پرسه کدوم ارز
  ۵) تحلیل رو اجرا می‌کنه و نتیجه (به‌صلاح هست یا نه) رو می‌گه
"""

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler

from techniques import TECHNIQUES, ANALYZERS

WAITING_COIN_FOR_TECHNIQUE = 100


async def techniques_menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton(label, callback_data=f"tech:{key}")]
        for key, label in TECHNIQUES.items()
    ]
    await update.message.reply_text(
        "کدوم تکنیک رو می‌خوای اجرا کنم؟",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def technique_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    technique_key = query.data.split(":", 1)[1]
    if technique_key not in ANALYZERS:
        await query.edit_message_text("این تکنیک پیدا نشد.")
        return ConversationHandler.END

    context.user_data["selected_technique"] = technique_key
    await query.edit_message_text(
        f"{TECHNIQUES[technique_key]}\n\nنماد ارز رو بگو (مثلاً BTC، XRP، ADA):"
    )
    return WAITING_COIN_FOR_TECHNIQUE


async def receive_coin_for_technique(update: Update, context: ContextTypes.DEFAULT_TYPE):
    coin = update.message.text.strip().upper()
    binance_symbol = f"{coin}USDT"
    technique_key = context.user_data.get("selected_technique")

    if technique_key not in ANALYZERS:
        await update.message.reply_text("یه مشکلی پیش اومد، دوباره از منو شروع کن.")
        context.user_data.clear()
        return ConversationHandler.END

    await update.message.reply_text("در حال بررسی، چند ثانیه صبر کن...")

    analyzer = ANALYZERS[technique_key]
    result = analyzer(binance_symbol)

    if not result.get("ok"):
        await update.message.reply_text(f"❌ {result.get('message', 'خطای نامشخص')}")
        context.user_data.clear()
        return ConversationHandler.END

    verdict = "✅ به‌نظر به‌صلاحه" if result.get("favorable") else "⚪ سیگنال خاصی نیست"
    await update.message.reply_text(
        f"{TECHNIQUES[technique_key]} — {coin}\n\n"
        f"{result['message']}\n\n"
        f"📌 جمع‌بندی: {verdict}\n\n"
        f"⚠️ این فقط یه تحلیل تکنیکاله، نه توصیه‌ی مالی. تصمیم نهایی با خودته."
    )

    context.user_data.clear()
    return ConversationHandler.END


async def cancel_technique(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("لغو شد.")
    return ConversationHandler.END
