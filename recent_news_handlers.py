# -*- coding: utf-8 -*-
"""
دستور /recent — خبرهای مهم ۶ ساعت اخیر رو همین الان می‌گیره و تحلیل می‌کنه،
بدون نیاز به منتظر ماندن برای چرخه‌ی خودکار.
"""

from telegram import Update
from telegram.ext import ContextTypes

from news import fetch_recent_news, build_news_response
from db import get_user_settings, get_watchlist

HOURS_WINDOW = 6
MAX_ITEMS_TO_SEND = 5


async def recent_news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"در حال بررسی اخبار {HOURS_WINDOW} ساعت اخیر، چند ثانیه صبر کن...")

    important, raw_count, window_count = fetch_recent_news(hours=HOURS_WINDOW)

    if not important:
        await update.message.reply_text(
            f"📭 تو {HOURS_WINDOW} ساعت اخیر ({window_count} خبر بررسی شد از مجموع {raw_count} خبر خام)، "
            f"هیچ خبر مهمی با ارز قابل‌شناسایی پیدا نشد."
        )
        return

    await update.message.reply_text(
        f"📬 {len(important)} خبر مهم تو {HOURS_WINDOW} ساعت اخیر پیدا شد. ارسال می‌کنم..."
    )

    settings = get_user_settings(update.effective_user.id)
    watchlist = get_watchlist(update.effective_user.id)

    sent = 0
    for item in important:
        if sent >= MAX_ITEMS_TO_SEND:
            remaining = len(important) - sent
            await update.message.reply_text(f"... و {remaining} خبر دیگه هم بود (برای جلوگیری از شلوغی، فقط {MAX_ITEMS_TO_SEND} تای اول فرستاده شد).")
            break
        for coin in item["coins"]:
            message, code = build_news_response(item, coin, settings, watchlist)
            if message:
                await update.message.reply_text(message, parse_mode="HTML")
                sent += 1
