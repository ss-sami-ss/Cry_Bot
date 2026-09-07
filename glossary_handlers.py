# -*- coding: utf-8 -*-
"""دکمه‌ی «📖 اصطلاحات» — راهنمای کامل کلمات و اختصارات استفاده‌شده تو ربات."""

from telegram import Update
from telegram.ext import ContextTypes

from glossary import GLOSSARY_TEXT_PART1, GLOSSARY_TEXT_PART2


async def glossary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # چون کل متن از محدودیت یه پیام تلگرام رد می‌شه، دو تا پیام پشت‌سرهم می‌فرستیم
    await update.message.reply_text(GLOSSARY_TEXT_PART1)
    await update.message.reply_text(GLOSSARY_TEXT_PART2)
