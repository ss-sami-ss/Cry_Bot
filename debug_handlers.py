# -*- coding: utf-8 -*-
"""
دستور /testnews — یه تست مستقیم و فوری فید خبری، بدون نیاز به منتظر ماندن
برای چرخه‌ی خودکار (هر ۱۰ دقیقه). جواب کامل رو تو خود تلگرام می‌ده.
"""

from telegram import Update
from telegram.ext import ContextTypes

from news import debug_fetch_news
from translation import translate_to_persian


async def testnews_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("در حال تست مستقیم فید خبری، چند ثانیه صبر کن...")

    # تست جدا و صریح ترجمه — این‌جوری همیشه معلومه ترجمه کار می‌کنه یا نه
    test_translation = translate_to_persian(
        "SEC approves Bitcoin ETF after years of delay", cache_key="__test__"
    )
    translation_ok = test_translation != "SEC approves Bitcoin ETF after years of delay"
    translation_status = f"✅ کار می‌کنه — نمونه: «{test_translation}»" if translation_ok else "❌ کار نمی‌کنه — متن انگلیسی برگشت (به کنسول ربات نگاه کن ببین چه خطایی داد)"

    result = debug_fetch_news()

    if result["error"]:
        await update.message.reply_text(
            f"🌐 تست ترجمه: {translation_status}\n\n"
            f"❌ خطا در گرفتن اخبار:\n{result['error']}\n\n"
            f"اگه کد وضعیت (status code) بالا 401 یا 403 بود، یعنی COINSTATS_API_KEY "
            f"اشتباهه — دوباره از داشبورد openapi.coinstats.app چکش کن."
        )
        return

    lines = [
        f"🌐 تست ترجمه: {translation_status}",
        "",
        f"📡 وضعیت درخواست: {result['status_code']}",
        f"📰 تعداد خبر خام دریافتی: {result['raw_count']}",
        f"🔑 کلیدی که خبرها توش پیدا شد: {result['found_key']}",
        f"📂 کلیدهای موجود تو ریشه‌ی پاسخ: {result['top_keys']}",
    ]

    if result["sample_titles"]:
        lines.append("\nنمونه‌ی چندتا عنوان خبر (برای اطمینان از اتصال):")
        for t in result["sample_titles"]:
            lines.append(f"• {t}")

    lines.append(f"\n🔑 تعداد خبرهایی که با کلمات کلیدی «مهم» مطابقت داشتن: {result['keyword_match_count']}")

    if result["coin_matches"]:
        lines.append(f"\n✅ {len(result['coin_matches'])} تا از این‌ها ارز قابل‌شناسایی هم داشتن:")
        for title, coins in result["coin_matches"][:5]:
            lines.append(f"• [{', '.join(coins)}] {title}")
    else:
        lines.append("\n⚠️ هیچ‌کدوم ارز قابل‌شناسایی نداشتن.")

    await update.message.reply_text("\n".join(lines))
