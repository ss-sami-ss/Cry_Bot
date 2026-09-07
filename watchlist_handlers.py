# -*- coding: utf-8 -*-
"""
مدیریت واچ‌لیست پویا: اضافه/حذف/نمایش ارزهای تحت‌نظر از طریق دستورات تلگرام.
هر کاربر واچ‌لیست کاملاً مستقل و شخصی خودش رو داره — اضافه/حذف یه نفر
هیچ تأثیری روی بقیه‌ی کاربرها نداره.

هر دستور دو حالت داره:
  - با آرگومان مستقیم: /watch ADA  -> فوری اجرا می‌شه
  - بدون آرگومان: /watch  -> ربات می‌پرسه «نماد ارزو بگو» و منتظر جواب می‌مونه
"""

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from db import get_watchlist, add_to_watchlist, remove_from_watchlist
from indicators import get_klines

WAITING_WATCH_SYMBOL, WAITING_UNWATCH_SYMBOL = range(2)


def _to_binance_symbol(coin: str) -> str:
    return f"{coin.upper()}USDT"


async def _do_watch(update: Update, coin_raw: str):
    user_id = update.effective_user.id
    coin = coin_raw.strip().upper()
    symbol = _to_binance_symbol(coin)

    candles = get_klines(symbol, interval="1h", limit=2)
    if not candles:
        await update.message.reply_text(
            f"نماد {symbol} روی Binance پیدا نشد. مطمئن شو اسم ارز درسته (مثلاً ADA، DOGE، MATIC)."
        )
        return

    add_to_watchlist(user_id, coin, symbol)
    await update.message.reply_text(
        f"✅ {coin} به واچ‌لیست شخصی تو اضافه شد. از این به بعد خبرهاش رو کامل تحلیل می‌کنم "
        f"(این تغییر فقط برای خودته، رو بقیه‌ی کاربرها اثر نداره)."
    )


async def _do_unwatch(update: Update, coin_raw: str):
    user_id = update.effective_user.id
    coin = coin_raw.strip().upper()
    removed = remove_from_watchlist(user_id, coin)
    if removed:
        await update.message.reply_text(f"🗑️ {coin} از واچ‌لیست شخصی تو حذف شد.")
    else:
        await update.message.reply_text(f"{coin} اصلاً تو واچ‌لیست تو نبود.")


async def watch_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        await _do_watch(update, context.args[0])
        return ConversationHandler.END
    await update.message.reply_text("نماد ارزو بگو (مثلاً ADA):")
    return WAITING_WATCH_SYMBOL


async def watch_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _do_watch(update, update.message.text)
    return ConversationHandler.END


async def unwatch_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        await _do_unwatch(update, context.args[0])
        return ConversationHandler.END
    await update.message.reply_text("نماد ارزی که می‌خوای حذف کنی رو بگو (مثلاً ADA):")
    return WAITING_UNWATCH_SYMBOL


async def unwatch_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _do_unwatch(update, update.message.text)
    return ConversationHandler.END


async def cancel_watch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لغو شد.")
    return ConversationHandler.END


async def watchlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    watchlist = get_watchlist(user_id)
    if not watchlist:
        await update.message.reply_text("واچ‌لیست شخصی تو خالیه. با /watch [نماد] اضافه کن.")
        return

    coins = "، ".join(watchlist.keys())
    await update.message.reply_text(
        f"📋 ارزهای تحت‌نظر شخصی تو ({len(watchlist)} تا):\n{coins}\n\n"
        f"اضافه کردن: /watch [نماد]\n"
        f"حذف کردن: /unwatch [نماد]"
    )
