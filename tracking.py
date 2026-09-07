# -*- coding: utf-8 -*-
"""
پیگیری معامله: بعد از این‌که کاربر «بررسی معامله» رو زد و دکمه‌ی 📌 پیگیری رو فشرد،
ربات صبر می‌کنه تا افق زمانی تخمینی (نسبت به همون لحظه‌ای که دکمه رو زدی، نه زمان
انتشار خبر) بگذره، بعد قیمت لحظه‌ای رو با ورود/هدف/استاپ مقایسه می‌کنه و نتیجه رو
گزارش می‌ده — یعنی همون لحظه‌ی زدن دکمه، شروع می‌شه به جمع کردن داده و حساب کردن،
بدون توجه به این‌که خبر کِی منتشر شده بوده.

این پیگیری‌ها تو دیتابیس ذخیره می‌شن، پس حتی اگه ربات ری‌استارت بشه،
با اجرای reschedule_pending_tracks دوباره زمان‌بندی می‌شن و گم نمی‌شن.
"""

from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.ext import ContextTypes

from db import (
    get_analysis,
    save_tracked_trade,
    get_pending_tracked_trades,
    mark_tracked_trade_done,
    get_user_settings,
)
from indicators import get_current_price
from formatting import format_datetime
from config import CHANNEL_ID

DEFAULT_FALLBACK_HOURS = 6


def _parse_iso(dt_str):
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


async def track_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    code = query.data.split(":", 1)[1]

    analysis = get_analysis(code)
    if analysis is None:
        await query.answer("این کد پیدا نشد یا قدیمیه.", show_alert=True)
        return

    await query.answer("📌 پیگیری فعال شد.")

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    settings = get_user_settings(user_id)

    # مبنا: همین لحظه‌ی زدن دکمه — کاری به زمان انتشار خبر نداریم
    start_time = datetime.now(timezone.utc)
    hours = analysis.get("time_horizon_hours") or DEFAULT_FALLBACK_HOURS
    track_at = start_time + timedelta(hours=hours)

    tracked_id = save_tracked_trade(code, user_id, chat_id, track_at.isoformat(), start_time.isoformat())

    delay_seconds = max(5, (track_at - start_time).total_seconds())
    context.job_queue.run_once(
        check_tracked_trade_job,
        when=delay_seconds,
        data={"tracked_id": tracked_id, "code": code, "chat_id": chat_id, "user_id": user_id, "start_time_iso": start_time.isoformat()},
    )

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"📌 پیگیری معامله {code} فعال شد.\n\n"
            f"⏱️ از همین الان ({format_datetime(start_time, settings)})، "
            f"بعد از {hours:.1f} ساعت چک می‌کنم: {format_datetime(track_at, settings)}"
        ),
    )


async def check_tracked_trade_job(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    tracked_id = data["tracked_id"]
    code = data["code"]
    chat_id = data["chat_id"]
    user_id = data["user_id"]
    start_time_iso = data.get("start_time_iso")

    analysis = get_analysis(code)
    if analysis is None:
        mark_tracked_trade_done(tracked_id)
        return

    coin = analysis["coin"]
    symbol = f"{coin}USDT"
    entry = analysis["price"]
    target = analysis.get("target")
    stop = analysis.get("stop_loss")
    direction = analysis.get("direction", "LONG")

    current = get_current_price(symbol)
    if current is None:
        await context.bot.send_message(chat_id=chat_id, text=f"⚠️ نشد قیمت فعلی {coin} رو برای پیگیری {code} بگیرم — دوباره امتحان کن.")
        return

    # منطق بررسی هدف/استاپ و محاسبه‌ی سود/زیان باید جهت معامله رو در نظر بگیره —
    # تو شورت، هدف پایین‌تر از ورود و استاپ بالاترشه (برعکس لانگ)، پس شرط‌ها هم برعکس می‌شن.
    if direction == "SHORT":
        if target and current <= target:
            outcome_line = "🎯 هدف خورد"
        elif stop and current >= stop:
            outcome_line = "🛑 استاپ خورد"
        else:
            outcome_line = "⏳ نه به هدف رسیده نه استاپ خورده — قیمت هنوز بین این دو محدوده‌ست"
        pnl_percent = ((entry - current) / entry * 100) if entry else None
    else:
        if target and current >= target:
            outcome_line = "🎯 هدف خورد"
        elif stop and current <= stop:
            outcome_line = "🛑 استاپ خورد"
        else:
            outcome_line = "⏳ نه به هدف رسیده نه استاپ خورده — قیمت هنوز بین این دو محدوده‌ست"
        pnl_percent = ((current - entry) / entry * 100) if entry else None

    settings = get_user_settings(user_id)
    start_time = _parse_iso(start_time_iso) or datetime.now(timezone.utc)
    now = datetime.now(timezone.utc)
    elapsed_hours = (now - start_time).total_seconds() / 3600

    from indicators import direction_label
    message = (
        f"📌 نتیجه‌ی پیگیری {code} ({coin})\n"
        f"{direction_label(direction)}\n\n"
        f"از لحظه‌ی فعال‌کردن پیگیری ({format_datetime(start_time, settings)})، "
        f"بعد از گذشت {elapsed_hours:.1f} ساعت:\n\n"
        f"📥 ورود: {entry} | 🎯 هدف: {target} | 🛑 استاپ: {stop}\n"
        f"📊 قیمت فعلی: {current}\n\n"
        f"{outcome_line}\n"
        f"💹 سود/زیان نسبت به ورود: {pnl_percent:+.2f}٪"
    )

    await context.bot.send_message(chat_id=chat_id, text=message)

    if CHANNEL_ID:
        try:
            await context.bot.send_message(chat_id=CHANNEL_ID, text=message)
        except Exception as e:
            print(f"[خطا در ارسال نتیجه‌ی پیگیری به کانال] {e}")

    mark_tracked_trade_done(tracked_id)


def reschedule_pending_tracks(application):
    """
    موقع بالا اومدن ربات صدا زده می‌شه — هر پیگیری‌ای که هنوز انجام نشده رو
    دوباره زمان‌بندی می‌کنه، تا با ری‌استارت ربات گم نشه.
    """
    pending = get_pending_tracked_trades()
    now = datetime.now(timezone.utc)

    for trade in pending:
        track_at = _parse_iso(trade["track_at"])
        if track_at is None:
            continue
        delay_seconds = max(5, (track_at - now).total_seconds())
        application.job_queue.run_once(
            check_tracked_trade_job,
            when=delay_seconds,
            data={
                "tracked_id": trade["id"],
                "code": trade["code"],
                "chat_id": trade["chat_id"],
                "user_id": trade["user_id"],
                "start_time_iso": trade.get("created_at"),
            },
        )

    if pending:
        print(f"[پیگیری] {len(pending)} پیگیری معلق دوباره زمان‌بندی شد.")
