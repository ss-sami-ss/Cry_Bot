# -*- coding: utf-8 -*-
"""
محدود کردن ربات فقط به یه (یا چندتا) کاربر مشخص.
تلگرام برای ربات‌ها «لینک دعوت خصوصی» نداره — هرکسی یوزرنیم ربات رو بدونه می‌تونه
بهش پیام بده. برای همین به‌جای محدود کردن دسترسی، خود ربات چک می‌کنه فرستنده مجازه یا نه؛
اگه نبود، کاملاً بی‌صدا نادیده‌ش می‌گیره (نه جواب می‌ده، نه اعلام می‌کنه ربات وجود داره).
"""

from telegram import Update
from telegram.ext import ContextTypes, ApplicationHandlerStop

from config import AUTHORIZED_USER_IDS


async def check_authorization(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not AUTHORIZED_USER_IDS:
        # اگه هیچ‌کس تو لیست مجازها تنظیم نشده، برای امنیت، این یعنی هیچ‌کس اجازه نداره
        raise ApplicationHandlerStop

    user = update.effective_user
    if user is None or user.id not in AUTHORIZED_USER_IDS:
        # بی‌صدا نادیده می‌گیریم — حتی یه پیام خطا هم برنمی‌گردونیم که وجود ربات لو نره
        raise ApplicationHandlerStop
    # اگه مجاز بود، اجازه می‌ده پردازش به هندلرهای بعدی ادامه پیدا کنه (کاری انجام نمی‌ده)
