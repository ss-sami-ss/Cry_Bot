# -*- coding: utf-8 -*-
"""
فرمت دوم برای محاسبه‌ی ریسک: مکالمه‌ای، مرحله‌به‌مرحله.
کاربر می‌نویسه "محاسبه معامله"، ربات به‌ترتیب می‌پرسه:
  ۱) کد معامله
  ۲) سرمایه (Capital)
  ۳) درصد ریسک (Risk)
و در آخر نتیجه رو می‌ده — دقیقاً همون محاسبه‌ای که فرمت تک‌خطی هم انجام می‌ده.
"""

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler

from db import get_analysis, get_user_settings
from risk import calculate_position_size
from handlers import normalize_digits, build_risk_reply
from config import CHANNEL_ID

# سه مرحله‌ی مکالمه
WAITING_CODE, WAITING_CAPITAL, WAITING_RISK = range(3)


async def start_calc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "بریم محاسبه کنیم 🧮\n\nکد معامله رو بفرست (مثلاً NWS-011):"
    )
    return WAITING_CODE


async def start_calc_from_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    نقطه‌ی ورود جایگزین — وقتی کاربر رو دکمه‌ی «🧮 محاسبه معامله» زیر خبر می‌زنه.
    کد از قبل تو callback_data هست، پس نیازی به پرسیدنش نیست — مستقیم می‌ره سراغ سرمایه.
    """
    query = update.callback_query
    await query.answer()

    code = query.data.split(":", 1)[1]
    analysis = get_analysis(code)

    if analysis is None:
        await query.message.reply_text(f"کد {code} پیدا نشد یا قدیمیه.")
        return ConversationHandler.END

    context.user_data.clear()
    context.user_data["calc_code"] = code
    context.user_data["calc_analysis"] = analysis

    await query.message.reply_text(
        f"بریم محاسبه کنیم برای {code} 🧮\n\nسرمایه‌ت (Capital) رو به دلار بفرست (مثلاً 1000):"
    )
    return WAITING_CAPITAL


async def receive_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    analysis = get_analysis(code)

    if analysis is None:
        await update.message.reply_text(
            f"کد {code} پیدا نشد. دوباره کد رو بفرست، یا برای لغو بنویس /cancel"
        )
        return WAITING_CODE

    context.user_data["calc_code"] = code
    context.user_data["calc_analysis"] = analysis
    await update.message.reply_text("سرمایه‌ت (Capital) رو به دلار بفرست (مثلاً 1000):")
    return WAITING_CAPITAL


async def receive_capital(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = normalize_digits(update.message.text.strip())
    try:
        capital = float(text)
    except ValueError:
        await update.message.reply_text(
            "این عدد نبود. سرمایه‌ت (Capital) رو فقط به‌صورت عدد بفرست (مثلاً 1000):"
        )
        return WAITING_CAPITAL

    context.user_data["calc_capital"] = capital
    await update.message.reply_text(
        "درصد ریسک (Risk) که حاضری تو این معامله بپذیری رو بفرست (مثلاً 2):"
    )
    return WAITING_RISK


async def receive_risk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = normalize_digits(update.message.text.strip())
    try:
        risk_percent = float(text)
    except ValueError:
        await update.message.reply_text(
            "این عدد نبود. درصد ریسک (Risk) رو فقط به‌صورت عدد بفرست (مثلاً 2):"
        )
        return WAITING_RISK

    code = context.user_data.get("calc_code")
    capital = context.user_data.get("calc_capital")
    analysis = context.user_data.get("calc_analysis")

    result = calculate_position_size(
        capital=capital,
        risk_percent=risk_percent,
        entry_price=analysis["price"],
        stop_loss_price=analysis["stop_loss"],
    )

    if result is None:
        await update.message.reply_text("محاسبه ممکن نشد — داده‌ی استاپ‌لاس این تحلیل ناقصه.")
    else:
        settings = get_user_settings(update.effective_user.id)
        reply_text = build_risk_reply(code, analysis, capital, risk_percent, result, settings)
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("📌 پیگیری", callback_data=f"track:{code}")]])
        await update.message.reply_text(reply_text, reply_markup=keyboard)

        if CHANNEL_ID:
            try:
                await context.bot.send_message(chat_id=CHANNEL_ID, text=reply_text)
            except Exception as e:
                print(f"[خطا در ارسال به کانال] {e}")

    context.user_data.clear()
    return ConversationHandler.END


async def cancel_calc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("محاسبه لغو شد.")
    return ConversationHandler.END
