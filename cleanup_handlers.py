# -*- coding: utf-8 -*-
"""
پاک‌سازی دستی تحلیل‌های قدیمی از دیتابیس.
دو حالت ورودی:
  - با آرگومان: /clearold 30      -> فوری پیش‌نمایش می‌ده
  - بدون آرگومان: /clearold       -> می‌پرسه «تا چند روز؟»
و همیشه یه مرحله‌ی تأیید قبل از پاک‌سازی واقعی هست:
  /clearold 30 تایید -> واقعاً پاک می‌کنه
"""

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from db import count_analyses_older_than, delete_analyses_older_than

WAITING_DAYS = 0


def _parse_and_preview_or_delete(args):
    days = 30
    confirmed = False
    for arg in args:
        if arg in ("تایید", "تأیید", "confirm"):
            confirmed = True
        elif arg.isdigit():
            days = int(arg)
    return days, confirmed


async def _run_clearold(update: Update, args):
    days, confirmed = _parse_and_preview_or_delete(args)
    count = count_analyses_older_than(days)

    if count == 0:
        await update.message.reply_text(f"هیچ تحلیل قدیمی‌تر از {days} روز پیدا نشد — نیازی به پاک‌سازی نیست.")
        return

    if not confirmed:
        await update.message.reply_text(
            f"📦 {count} تا تحلیل قدیمی‌تر از {days} روز پیدا شد.\n\n"
            f"⚠️ توجه: کدهایی که پاک بشن دیگه قابل بازیابی نیستن.\n\n"
            f"برای پاک‌سازی قطعی بفرست:\n/clearold {days} تایید"
        )
        return

    deleted = delete_analyses_older_than(days)
    await update.message.reply_text(f"🗑️ {deleted} تا تحلیل قدیمی‌تر از {days} روز پاک شد.")


async def clearold_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        await _run_clearold(update, context.args)
        return ConversationHandler.END
    await update.message.reply_text("تا چند روز قبل رو پاک کنم؟ یه عدد بفرست (مثلاً 30):")
    return WAITING_DAYS


async def clearold_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    await _run_clearold(update, [text])
    return ConversationHandler.END


async def cancel_clearold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لغو شد.")
    return ConversationHandler.END
