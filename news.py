# -*- coding: utf-8 -*-
"""
گرفتن اخبار از CryptoPanic، فیلتر کردن خبرهای مهم، و ساخت تحلیل کامل
(خبر + فنی) برای ارسال به تلگرام.
"""

import requests
from datetime import datetime
from html import escape as html_escape
from zoneinfo import ZoneInfo
from config import (
    COINSTATS_API_KEY,
    RSI_PERIOD,
    ATR_PERIOD,
    KLINES_INTERVAL,
    TIMEZONE,
)
from indicators import (
    analyze_coin, rsi_short_tag, atr_short_tag, direction_label,
    get_base_technicals, finalize_trade_setup, build_no_trade_result,
    calculate_market_regime, calculate_multi_timeframe_regime,
)
from sentiment import get_fear_greed_index, interpret_fear_greed
from futures import get_funding_rate, get_open_interest_change, interpret_open_interest_change, funding_short_tag, get_long_short_ratio, long_short_short_tag
from confluence import build_confluence_summary, build_strength_bar_from_alignment, decide_direction_and_alignment, entry_timing_verdict
from techniques import get_technique_signals
from risk import calculate_position_size
from db import get_next_code, save_analysis, get_watchlist, is_news_seen, mark_news_seen
from formatting import format_datetime, format_money
from translation import translate_to_persian

# سرمایه و درصد ریسک فرضی، فقط برای نشون دادن یه *مثال* آموزشی در پیام —
# ربطی به سرمایه‌ی واقعی کاربر نداره. عدد واقعی همیشه از خود کاربر گرفته می‌شه.
EXAMPLE_CAPITAL = 1000
EXAMPLE_RISK_PERCENT = 2
EXAMPLE_CASH_ONLY = 100

# حداقل نسبت سیگنال هم‌جهت (نه عدد ثابت، چون تعداد کل سیگنال‌ها بین ۸ تا ۱۱ متغیره) که
# لازمه تا ربات قاطعانه لانگ/شورت پیشنهاد بده. کمتر از این، به‌جای هدف/استاپ ساختگی،
# می‌گه «سیگنال کافی واضح نیست». ۰.۵ یعنی معادل «۴ از ۸».
MIN_ALIGNED_SIGNALS = 3  # عدد خام (نه نسبت) — چون تو بک‌تست واقعی، ۵۰٪ عملاً هیچ‌وقت رد نمی‌شد

# نکته‌ی تاریخی: یه فیلتر حداقل R:R (رد کردن معامله اگه ریسک از ریوارد بیشتر بود)
# رو امتحان کردیم و برداشتیم — چون رو دو تا بک‌تست متفاوت نتیجه‌ی متناقضی داد
# (یه‌بار بهتر شد، یه‌بار بدتر). با نمونه‌ی فعلی (چندتا ده معامله) نمی‌شه قضاوت
# قابل‌اعتمادی درباره‌ش کرد — تا وقتی داده‌ی زنده‌ی بیشتری از پیگیری‌های واقعی
# جمع نشه، بدون این فیلتر ادامه می‌دیم که سرعت جمع‌آوری داده بیشتر باشه.
# (خودِ risk_reward همیشه محاسبه و ذخیره می‌شه، پس هروقت داده‌ی زنده‌ی کافی
# جمع شد، می‌شه رو همون داده تصمیم گرفت این فیلتر واقعاً کمک می‌کنه یا نه.)


def _invisible_link(url):
    """
    یه لینک با متن «نامرئی» (فقط یه کاراکتر خیلی‌کوچیک، نه فاصله‌ی خالی که تلگرام حذفش می‌کنه) —
    باعث می‌شه تلگرام کارت پیش‌نمایش (عکس+عنوان سایت) رو بسازه، بدون این‌که خودِ
    لینک به‌صورت متن آبی قابل‌مشاهده تو پیام نشون داده بشه. برای کارکردنش، باید
    پیام با parse_mode="HTML" ارسال بشه.
    """
    return f'<a href="{html_escape(url)}">\u2063</a>'


def _regime_line(data):
    """متن نمایش رژیم بازار، شامل تعداد تایم‌فریم‌های تأییدکننده."""
    if data.get("regime") == "TRENDING":
        direction = data.get("trend_direction") or ""
        agree = data.get("regime_agree")
        checked = data.get("regime_checked")
        return f"روند {direction} ({agree}/{checked} تایم‌فریم تأیید)"
    return "رنج/بی‌جهت"


def _laddered_targets_block(tech):
    """
    خط هدف‌های پله‌ای — به‌جای یه هدف تکی، ۳ سطح با درصد پیشنهادی برای بستن هرکدوم.
    اگه فقط یه هدف تکی می‌خوای (نه پله‌ای)، از هدف ۲ (وسطی) استفاده کن —
    بهترین تعادل بین احتمال رسیدن و میزان سود.
    """
    if not tech.get("target_1"):
        return f"🎯 هدف: {tech.get('target')}"

    return (
        f"🎯 هدف‌های پله‌ای (Laddered):\n"
        f"  ① {tech['target_1']} — پیشنهاد بستن {tech['target_1_close_pct']}٪ پوزیشن (احتمال بالا)\n"
        f"  ② {tech['target_2']} — پیشنهاد بستن {tech['target_2_close_pct']}٪ پوزیشن (هدف اصلی)\n"
        f"  ③ {tech['target_3']} — پیشنهاد بستن {tech['target_3_close_pct']}٪ پوزیشن (اگه روند قوی ادامه پیدا کنه)\n"
        f"  💡 استاپ پله‌ای می‌ره جلو، هر بار یه سود بیشتر قفل می‌شه:\n"
        f"     بعد از ①  → استاپ می‌ره رو نقطه‌ی ورود (Break-even، دیگه بدترین حالت سود صفره)\n"
        f"     بعد از ②  → استاپ می‌ره رو ① (بدترین حالت الان سود همون ①ه)\n"
        f"     بعد از ③  → کل پوزیشن بسته شده\n"
        f"  ℹ️ برای معامله‌ی تک‌هدفه (نه پله‌ای)، هدف ② رو در نظر بگیر"
    )


def _now_tehran_str():
    """تاریخ و ساعت فعلی به وقت تهران، برای درج در پیام خبر."""
    now = datetime.now(ZoneInfo(TIMEZONE))
    weekdays_fa = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]
    weekday_name = weekdays_fa[now.weekday()]
    return f"{weekday_name} {now.strftime('%Y-%m-%d %H:%M')} (به وقت تهران)"

COINSTATS_NEWS_URL = "https://openapiv1.coinstats.app/news"

# کلمات کلیدی که معمولاً نشونه‌ی خبر تکون‌دهنده‌ی بازارن
IMPORTANT_KEYWORDS = [
    "hack", "exploit", "sec", "etf", "approval", "ban", "lawsuit",
    "liquidation", "regulation", "crash", "surge", "listing", "delisting",
]

# نگاشت اسم کامل ارز به نمادش — چون فیلد "coins" در پاسخ CoinStats قابل‌اعتماد نیست،
# مستقیم از روی متن خبر (اسم یا نماد) تشخیص می‌دیم کدوم ارزها ذکر شدن.
NAME_TO_TICKER = {
    "bitcoin": "BTC", "ethereum": "ETH", "ripple": "XRP", "xrp": "XRP",
    "solana": "SOL", "cardano": "ADA", "dogecoin": "DOGE", "litecoin": "LTC",
    "polkadot": "DOT", "chainlink": "LINK", "avalanche": "AVAX",
    "polygon": "MATIC", "binance coin": "BNB", "tron": "TRX",
    "shiba inu": "SHIB", "cosmos": "ATOM", "stellar": "XLM", "uniswap": "UNI",
    "near protocol": "NEAR", "filecoin": "FIL", "internet computer": "ICP",
    "hedera": "HBAR", "vechain": "VET", "algorand": "ALGO",
    "the sandbox": "SAND", "decentraland": "MANA", "aave": "AAVE",
    "maker": "MKR", "the graph": "GRT", "fantom": "FTM", "tezos": "XTZ",
    "monero": "XMR", "cronos": "CRO", "kava": "KAVA", "thorchain": "RUNE",
    "injective": "INJ", "sui": "SUI", "sei": "SEI", "celestia": "TIA",
    "pepe": "PEPE", "dogwifhat": "WIF", "bonk": "BONK", "arbitrum": "ARB",
    "optimism": "OP", "aptos": "APT",
}
# تیکرهای معتبر برای چک مستقیم تو متن (مثل "XRP" یا "BTC" که خودشون تو خبر اومدن)
_KNOWN_TICKERS = set(NAME_TO_TICKER.values())


def _extract_mentioned_coins(text):
    """از روی متن خبر (اسم کامل یا نماد ارز)، لیست نمادهای ذکرشده رو استخراج می‌کنه."""
    import re
    text_lower = text.lower()
    found = set()

    for name, ticker in NAME_TO_TICKER.items():
        if re.search(r"\b" + re.escape(name) + r"\b", text_lower):
            found.add(ticker)

    for ticker in _KNOWN_TICKERS:
        if re.search(r"\b" + ticker + r"\b", text, re.IGNORECASE):
            found.add(ticker)

    return found


# کلیدهای احتمالی مختلف که ممکنه CoinStats توشون لیست خبرها رو برگردونه —
# چون مطمئن نبودیم دقیقاً کدومه، همه‌شون رو امتحان می‌کنیم.
_POSSIBLE_LIST_KEYS = ["news", "result", "data", "posts", "articles", "items"]


def _parse_news_list(data):
    """
    از روی پاسخ JSON (که ممکنه لیست باشه، دیکشنری با کلیدهای مختلف،
    یا حتی یه لایه تودرتو باشه)، لیست واقعی خبرها رو پیدا می‌کنه.
    برمی‌گردونه: (لیست_خبرها, مسیر_پیداشده_یا_None, کلیدهای_ریشه)
    """
    if isinstance(data, list):
        return data, "(خودِ ریشه یه لیست بود)", []

    if not isinstance(data, dict):
        return [], None, []

    top_keys = list(data.keys())

    # لایه‌ی اول
    for key in _POSSIBLE_LIST_KEYS:
        value = data.get(key)
        if isinstance(value, list):
            return value, key, top_keys

    # یه لایه تودرتو (مثلاً {"result": {"news": [...]}})
    for outer_key in _POSSIBLE_LIST_KEYS:
        outer_value = data.get(outer_key)
        if isinstance(outer_value, dict):
            for inner_key in _POSSIBLE_LIST_KEYS:
                inner_value = outer_value.get(inner_key)
                if isinstance(inner_value, list):
                    return inner_value, f"{outer_key}.{inner_key}", top_keys

    return [], None, top_keys


def _build_important_items(results, mark_seen=True):
    """
    از روی لیست خام خبرها، اونایی که هم کلمه‌ی کلیدی مهم دارن هم ارز قابل‌شناسایی،
    رو استخراج می‌کنه. با mark_seen=False می‌شه بدون اثرگذاری روی چرخه‌ی خودکار
    (که با جدول seen_news تو دیتابیس کار می‌کنه — نه فقط حافظه، که با ری‌استارت
    ربات پاک نشه و باعث تکراری اومدن خبر نشه) یه بار جدا این فیلتر رو اجرا کرد.
    """
    important = []
    matched_keyword_count = 0
    for post in results:
        news_id = post.get("id")
        if mark_seen and (not news_id or is_news_seen(news_id)):
            continue

        title = post.get("title", "")
        description = post.get("description", "")
        text = f"{title} {description}"

        if not any(kw in text.lower() for kw in IMPORTANT_KEYWORDS):
            continue
        matched_keyword_count += 1

        coins = list(_extract_mentioned_coins(text))
        if not coins:
            continue

        if mark_seen and news_id:
            mark_news_seen(news_id)

        important.append({
            "id": news_id,
            "title": title,
            "url": post.get("link", ""),
            "coins": coins,
            "raw": post,
        })

    return important, matched_keyword_count


def fetch_important_news():
    """
    گرفتن اخبار اخیر از CoinStats و فیلتر کردن اونایی که «مهم» تشخیص داده می‌شن.
    برخلاف قبل، دیگه محدود به واچ‌لیست نیست — هر ارزی که خبر مهمی داشته باشه برگردونده می‌شه؛
    تصمیم این‌که پیام کامل بفرسته یا فقط اطلاع‌رسانی کوتاه، در build_news_response گرفته می‌شه.
    """
    if not COINSTATS_API_KEY:
        print("[هشدار] COINSTATS_API_KEY تنظیم نشده — فید خبری غیرفعاله.")
        return []

    try:
        resp = requests.get(
            COINSTATS_NEWS_URL,
            headers={"X-API-KEY": COINSTATS_API_KEY},
            params={"limit": 30},
            timeout=10,
        )
        resp.raise_for_status()
        results, found_key, top_keys = _parse_news_list(resp.json())
        print(f"[دیباگ] {len(results)} خبر خام از CoinStats دریافت شد (کلید: {found_key}, کلیدهای موجود: {top_keys})")
    except Exception as e:
        print(f"[خطا در گرفتن اخبار] {e}")
        print(
            "[راهنما] اگه خطای 401 گرفتی، یعنی COINSTATS_API_KEY اشتباهه یا هنوز فعال نشده. "
            "از داشبورد https://openapi.coinstats.app کلید رو دوباره چک کن."
        )
        return []

    important, matched_keyword_count = _build_important_items(results, mark_seen=True)

    print(
        f"[دیباگ] {matched_keyword_count} خبر با کلمه‌ی کلیدی مهم مطابقت داشت، "
        f"{len(important)} تاشون ارز قابل‌شناسایی هم داشتن"
    )
    return important


# فیلدهای احتمالی که ممکنه تاریخ/زمان انتشار خبر توشون باشه
_POSSIBLE_DATE_FIELDS = ["publishedAt", "createdAt", "date", "feedDate", "publishDate", "time"]


def _parse_post_datetime(post):
    """تلاش برای استخراج تاریخ انتشار یه خبر، از هر فرمتی که باشه (ISO رشته‌ای یا timestamp عددی)."""
    from datetime import timezone

    for field in _POSSIBLE_DATE_FIELDS:
        val = post.get(field)
        if val is None:
            continue
        try:
            if isinstance(val, (int, float)):
                # بعضی APIها ثانیه می‌دن، بعضی میلی‌ثانیه
                if val > 1e12:
                    val = val / 1000
                return datetime.fromtimestamp(val, tz=timezone.utc)
            if isinstance(val, str):
                return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except Exception:
            continue
    return None


def fetch_recent_news(hours=6):
    """
    گرفتن خبرهای «مهم» منتشرشده در N ساعت اخیر — مستقل از چرخه‌ی خودکار،
    برای وقتی که خودت می‌خوای همین الان مرور کنی، نه منتظر پیام خودکار بمونی.
    برمی‌گردونه: (لیست_خبرهای_مهم, تعداد_خام, تعداد_در_بازه_زمانی)
    """
    from datetime import timezone, timedelta

    if not COINSTATS_API_KEY:
        return [], 0, 0

    try:
        resp = requests.get(
            COINSTATS_NEWS_URL,
            headers={"X-API-KEY": COINSTATS_API_KEY},
            params={"limit": 50},
            timeout=10,
        )
        resp.raise_for_status()
        results, _, _ = _parse_news_list(resp.json())
    except Exception as e:
        print(f"[خطا در گرفتن اخبار اخیر] {e}")
        return [], 0, 0

    raw_count = len(results)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    # فقط خبرهایی که تاریخشون قابل‌تشخیصه و تو بازه‌ی زمانی‌ان رو نگه می‌داریم.
    # اگه هیچ خبری تاریخ قابل‌تشخیص نداشت (یعنی API این فیلد رو نمی‌ده)،
    # به‌جای برگردوندن خالی، همون N تای اول رو در نظر می‌گیریم (چون این APIها معمولاً جدیدترین رو اول می‌دن).
    dated = [(post, _parse_post_datetime(post)) for post in results]
    has_any_date = any(d is not None for _, d in dated)

    if has_any_date:
        in_window = [post for post, d in dated if d is not None and d >= cutoff]
    else:
        in_window = results  # فال‌بک: فرض بر اینه که لیست از قبل به ترتیب جدید-به-قدیم مرتبه

    important, _ = _build_important_items(in_window, mark_seen=False)
    return important, raw_count, len(in_window)


def debug_fetch_news():
    """
    نسخه‌ی تشخیصی fetch_important_news — برای دستور /testnews.
    برخلاف نسخه‌ی اصلی، هیچی رو "دیده‌شده" علامت نمی‌زنه (که چرخه‌ی عادی خراب نشه)
    و جزئیات کامل هر مرحله رو برمی‌گردونه تا بشه فهمید مشکل کجاست.
    """
    result = {
        "error": None,
        "status_code": None,
        "raw_count": 0,
        "found_key": None,
        "top_keys": [],
        "sample_titles": [],
        "keyword_match_count": 0,
        "coin_matches": [],
    }

    if not COINSTATS_API_KEY:
        result["error"] = "COINSTATS_API_KEY تنظیم نشده"
        return result

    try:
        resp = requests.get(
            COINSTATS_NEWS_URL,
            headers={"X-API-KEY": COINSTATS_API_KEY},
            params={"limit": 15},
            timeout=10,
        )
        result["status_code"] = resp.status_code
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        result["error"] = str(e)
        return result

    results, found_key, top_keys = _parse_news_list(data)
    result["raw_count"] = len(results)
    result["found_key"] = found_key
    result["top_keys"] = top_keys
    result["sample_titles"] = [p.get("title", "(بدون عنوان)") for p in results[:5]]

    for post in results:
        title = post.get("title", "")
        description = post.get("description", "")
        text = f"{title} {description}"

        if any(kw in text.lower() for kw in IMPORTANT_KEYWORDS):
            result["keyword_match_count"] += 1
            coins = _extract_mentioned_coins(text)
            if coins:
                result["coin_matches"].append((title, list(coins)))

    return result


def build_news_response(news_item, coin, settings=None, watchlist=None):
    """
    برای یه ارز مشخص تصمیم می‌گیره: اگه تو واچ‌لیستِ همون کاربره پیام کامل بسازه،
    اگه نیست فقط یه پیام کوتاه «کشف خبر» بسازه.
    settings=None یعنی پیش‌فرض (تهران/میلادی/دلار). watchlist باید از بیرون
    (مخصوص همون user_id) پاس داده بشه — چون واچ‌لیست دیگه سراسری نیست، شخصیه.
    """
    if settings is None:
        settings = {"calendar": "gregorian", "timezone": "Asia/Tehran", "currency": "USD", "toman_rate": None}
    if watchlist is None:
        watchlist = {}

    if coin in watchlist:
        data = compute_analysis_data(news_item, coin, watchlist[coin])
        if data is None:
            return None, None
        return render_analysis_text(data, settings), data["code"]

    return build_discovery_message(news_item, coin, settings), None


def build_discovery_message(news_item, coin, settings=None):
    """پیام کوتاه برای خبر مهمِ ارزی که تحت‌نظر نیست."""
    if settings is None:
        settings = {"calendar": "gregorian", "timezone": "Asia/Tehran", "currency": "USD", "toman_rate": None}

    published_at = _get_published_at(news_item) or datetime.now(ZoneInfo("UTC"))
    title_fa = translate_to_persian(news_item["title"], cache_key=news_item.get("id"))
    url = news_item.get("url", "")

    return (
        f"{_invisible_link(url) if url else ''}"
        f"🔎 خبر مهمی برای {coin} پیدا شد (تحت‌نظرت نیست):\n"
        f"«{html_escape(title_fa)}»\n"
        f"🕒 {format_datetime(published_at, settings)}\n\n"
        f"اگه می‌خوای از این به بعد {coin} رو هم زیر نظر بگیرم، بفرست:\n"
        f"/watch {coin}"
    )


def _get_published_at(news_item):
    """زمان انتشار خبر رو از داده‌ی خام (raw) استخراج می‌کنه، اگه موجود باشه."""
    from datetime import timezone as _tz
    raw = news_item.get("raw")
    if not raw:
        return None
    dt = _parse_post_datetime(raw)
    if dt and dt.tzinfo is None:
        dt = dt.replace(tzinfo=_tz.utc)
    return dt


def compute_standalone_analysis(coin, binance_symbol):
    """
    تحلیل فوری و مستقل از خبر — برای وقتی که خودت (نه یه خبر) می‌خوای همین الان
    وضعیت یه ارز رو بررسی کنی. دقیقاً همون موتور تحلیلی خبرها رو استفاده می‌کنه،
    فقط بدون بخش‌های مخصوص خبر (عنوان/لینک/زمان انتشار مقاله).
    """
    from datetime import timezone as _tz

    interval_labels = {"1h": "یک‌ساعته", "4h": "چهارساعته", "1d": "روزانه"}
    interval_label = interval_labels.get(KLINES_INTERVAL, KLINES_INTERVAL)

    base = get_base_technicals(binance_symbol, period=RSI_PERIOD, interval=KLINES_INTERVAL)
    if base is None:
        return None

    fg_value, fg_label = get_fear_greed_index()
    funding_rate = get_funding_rate(binance_symbol)
    oi_change = get_open_interest_change(binance_symbol)
    ls_ratio = get_long_short_ratio(binance_symbol)
    volume_ratio = base.get("volume_ratio")
    volume_direction = base.get("volume_direction")
    ma_trend_percent = base.get("ma_trend_percent")
    technique_flags = get_technique_signals(binance_symbol)
    regime, trend_direction, regime_agree, regime_checked = calculate_multi_timeframe_regime(binance_symbol)

    direction, aligned_count, total_signals = decide_direction_and_alignment(
        base["rsi"], funding_rate, fg_value, base["price"], base["support"], base["resistance"], oi_change,
        ls_ratio, volume_ratio, volume_direction, ma_trend_percent, technique_flags,
        regime, trend_direction,
    )

    no_trade = aligned_count < MIN_ALIGNED_SIGNALS
    if no_trade:
        tech = build_no_trade_result(base, reason=f"سیگنال کافی واضح نیست (کمتر از {MIN_ALIGNED_SIGNALS} از {total_signals})")
    else:
        tech = finalize_trade_setup(
            binance_symbol, base, direction,
            period=RSI_PERIOD, interval=KLINES_INTERVAL, interval_label=interval_label,
        )

    confluence_summary = build_confluence_summary(
        tech["rsi"], funding_rate, fg_value, tech["price"], tech["support"], tech["resistance"], oi_change,
        ls_ratio, volume_ratio, volume_direction, ma_trend_percent, technique_flags,
        regime, trend_direction,
    )
    strength_bar = build_strength_bar_from_alignment(aligned_count, total_signals)
    verdict = entry_timing_verdict(aligned_count, total_signals, direction)

    now = datetime.now(_tz.utc)

    example = None
    if not no_trade:
        example = calculate_position_size(
            capital=EXAMPLE_CAPITAL,
            risk_percent=EXAMPLE_RISK_PERCENT,
            entry_price=tech["price"],
            stop_loss_price=tech["stop_loss"],
        )

    # وقتی سیگنال کافی نیست، اصلاً کد/رکورد تحلیل نمی‌سازیم — چون چیزی برای
    # محاسبه‌ی حجم پوزیشن یا پیگیری وجود نداره (نه هدف، نه استاپ).
    code = None
    if not no_trade:
        code = get_next_code()
        save_analysis(code, coin, {
            "news_title": f"تحلیل دستی {coin}",
            "news_title_fa": f"تحلیل دستی {coin}",
            "news_url": "",
            "fear_greed": fg_value,
            "funding_rate": funding_rate,
            "open_interest_change": oi_change,
            "ls_ratio": ls_ratio,
            "volume_ratio": volume_ratio,
            "volume_direction": volume_direction,
            "ma_trend_percent": ma_trend_percent,
            "published_at": now.isoformat(),
            **tech,
        })

    return {
        "code": code,
        "coin": coin,
        "tech": tech,
        "fg_value": fg_value,
        "fg_label": fg_label,
        "funding_rate": funding_rate,
        "oi_change": oi_change,
        "ls_ratio": ls_ratio,
        "volume_ratio": volume_ratio,
        "volume_direction": volume_direction,
        "ma_trend_percent": ma_trend_percent,
        "aligned_count": aligned_count,
        "total_signals": total_signals,
        "regime": regime,
        "trend_direction": trend_direction,
        "regime_agree": regime_agree,
        "regime_checked": regime_checked,
        "confluence_summary": confluence_summary,
        "strength_bar": strength_bar,
        "verdict": verdict,
        "example": example,
        "published_at": now,
    }


def render_standalone_text(data, settings):
    """نمایش متن تحلیل مستقل — همون فرمت خبر، بدون بخش‌های مخصوص خبر، با یه جمع‌بندی مستقیم اضافه."""
    tech = data["tech"]
    code = data["code"]
    coin = data["coin"]

    header = (
        f"🔬 تحلیل دستی: {coin}\n"
        f"🕒 {format_datetime(data['published_at'], settings)}\n"
        f"{'[کد: ' + code + ']' if code else ''}\n\n"
    )

    if tech.get("no_trade"):
        reason = tech.get("no_trade_reason", "سیگنال کافی واضح نیست")
        return (
            f"{header}"
            f"{direction_label('NEUTRAL')}\n\n"
            f"📊 قیمت فعلی: {tech['price']} | RSI: {tech['rsi']} ({rsi_short_tag(tech['rsi'])})\n"
            f"🧱 نقاط کلیدی بازار: حمایت: {tech['support']} | مقاومت: {tech['resistance']}\n"
            f"📈 رژیم بازار: {_regime_line(data)}\n\n"
            f"{data['confluence_summary']}\n\n"
            f"{data['strength_bar']}\n\n"
            f"⚪ علت: {reason}\n"
            f"برای همین ربات هیچ هدف/استاپ ساختگی پیشنهاد نمی‌ده. صبر کردن برای یه ست‌آپ واضح‌تر منطقی‌تره."
        )

    example_block = ""
    if data["example"]:
        example = data["example"]
        leverage = example["required_leverage"]
        if leverage is not None and leverage <= 1:
            leverage_line = "• اهرم لازم: نیازی نیست (حجم پوزیشن از سرمایه‌ی فرضی کمتره)"
        else:
            leverage_line = f"• اهرم لازم برای این سرمایه‌ی فرضی: ~{leverage}x"

        example_block = (
            f"\n💰 مثال محاسبه (سرمایه فرضی {format_money(EXAMPLE_CAPITAL, settings)}, ریسک {EXAMPLE_RISK_PERCENT}٪):\n"
            f"• مبلغ در ریسک: {format_money(example['risk_amount'], settings)}\n"
            f"• حجم پوزیشن پیشنهادی: ~{format_money(example['position_size'], settings)}\n"
            f"{leverage_line}"
        )

    return (
        f"{header}"
        f"{direction_label(tech['direction'])}\n\n"
        f"📊 تحلیل فنی: RSI={tech['rsi']} ({rsi_short_tag(tech['rsi'])}) | "
        f"قیمت={tech['price']} | ATR={tech['atr']} ({atr_short_tag(tech['atr'], tech['price'])}, تایم‌فریم: {tech['atr_interval_label']})\n"
        f"😨 حس بازار: {data['fg_value']} ({data['fg_label']}) | "
        f"فاندینگ: {data['funding_rate']}٪ ({funding_short_tag(data['funding_rate'])}) | "
        f"تغییر پوزیشن باز (۲۴س): {data['oi_change']}٪\n"
        f"📊 نسبت لانگ/شورت: {data.get('ls_ratio')} ({long_short_short_tag(data.get('ls_ratio'))}) | "
        f"حجم: {data.get('volume_ratio')}× میانگین | "
        f"فاصله از MA۵۰: {data.get('ma_trend_percent')}٪\n"
        f"📐 سطوح معامله: استاپ: {tech['stop_loss']}{' 🧱' if tech.get('sr_used_for_stop') else ''} | R:R = 1:{tech['risk_reward']}\n"
        f"{_laddered_targets_block(tech)}\n"
        f"🧱 نقاط کلیدی بازار: حمایت: {tech['support']} | مقاومت: {tech['resistance']}\n"
        f"⏱️ افق زمانی: {tech['time_horizon']}\n\n"
        f"{data['confluence_summary']}\n"
        f"{example_block}\n\n"
        f"{data['strength_bar']}\n\n"
        f"📌 {data['verdict']}"
    )


def compute_analysis_data(news_item, coin, binance_symbol):
    """
    بخش «محاسبه»: تحلیل فنی کامل رو می‌سازه، ذخیره می‌کنه، و یه دیکشنری خام
    (بدون فرمت‌بندی متنی خاص یه کاربر) برمی‌گردونه. این تابع فقط یه‌بار
    برای هر خبر/ارز اجرا می‌شه؛ نمایشش برای هر کاربر جدا با render_analysis_text انجام می‌شه.

    ترتیب مهمه: اول داده‌ی پایه (RSI/قیمت/حمایت-مقاومت) گرفته می‌شه، بعد فاندینگ
    و Fear&Greed، بعد با ترکیب هر سه، جهت نهایی (لانگ/شورت) تعیین می‌شه —
    نه فقط بر پایه‌ی RSI تنها (که قبلاً باعث می‌شد اکثر معامله‌ها شورت پیشنهاد بشن).
    """
    from datetime import timezone as _tz

    interval_labels = {"1h": "یک‌ساعته", "4h": "چهارساعته", "1d": "روزانه"}
    interval_label = interval_labels.get(KLINES_INTERVAL, KLINES_INTERVAL)

    base = get_base_technicals(binance_symbol, period=RSI_PERIOD, interval=KLINES_INTERVAL)
    if base is None:
        return None

    fg_value, fg_label = get_fear_greed_index()
    funding_rate = get_funding_rate(binance_symbol)
    oi_change = get_open_interest_change(binance_symbol)
    ls_ratio = get_long_short_ratio(binance_symbol)
    volume_ratio = base.get("volume_ratio")
    volume_direction = base.get("volume_direction")
    ma_trend_percent = base.get("ma_trend_percent")
    technique_flags = get_technique_signals(binance_symbol)
    regime, trend_direction, regime_agree, regime_checked = calculate_multi_timeframe_regime(binance_symbol)

    direction, aligned_count, total_signals = decide_direction_and_alignment(
        base["rsi"], funding_rate, fg_value, base["price"], base["support"], base["resistance"], oi_change,
        ls_ratio, volume_ratio, volume_direction, ma_trend_percent, technique_flags,
        regime, trend_direction,
    )

    no_trade = aligned_count < MIN_ALIGNED_SIGNALS
    if no_trade:
        tech = build_no_trade_result(base, reason=f"سیگنال کافی واضح نیست (کمتر از {MIN_ALIGNED_SIGNALS} از {total_signals})")
    else:
        tech = finalize_trade_setup(
            binance_symbol, base, direction,
            period=RSI_PERIOD, interval=KLINES_INTERVAL, interval_label=interval_label,
        )

    confluence_summary = build_confluence_summary(
        tech["rsi"], funding_rate, fg_value, tech["price"], tech["support"], tech["resistance"], oi_change,
        ls_ratio, volume_ratio, volume_direction, ma_trend_percent, technique_flags,
        regime, trend_direction,
    )
    strength_bar = build_strength_bar_from_alignment(aligned_count, total_signals)

    published_at = _get_published_at(news_item) or datetime.now(_tz.utc)

    news_title_fa = translate_to_persian(news_item["title"], cache_key=news_item.get("id"))

    example = None
    if not no_trade:
        example = calculate_position_size(
            capital=EXAMPLE_CAPITAL,
            risk_percent=EXAMPLE_RISK_PERCENT,
            entry_price=tech["price"],
            stop_loss_price=tech["stop_loss"],
        )

    code = None
    if not no_trade:
        code = get_next_code()
        save_analysis(code, coin, {
            "news_title": news_item["title"],
            "news_title_fa": news_title_fa,
            "news_url": news_item["url"],
            "fear_greed": fg_value,
            "funding_rate": funding_rate,
            "open_interest_change": oi_change,
            "ls_ratio": ls_ratio,
            "volume_ratio": volume_ratio,
            "volume_direction": volume_direction,
            "ma_trend_percent": ma_trend_percent,
            "published_at": published_at.isoformat(),
            **tech,
        })

    return {
        "code": code,
        "coin": coin,
        "tech": tech,
        "fg_value": fg_value,
        "fg_label": fg_label,
        "funding_rate": funding_rate,
        "oi_change": oi_change,
        "ls_ratio": ls_ratio,
        "volume_ratio": volume_ratio,
        "volume_direction": volume_direction,
        "ma_trend_percent": ma_trend_percent,
        "aligned_count": aligned_count,
        "total_signals": total_signals,
        "regime": regime,
        "trend_direction": trend_direction,
        "regime_agree": regime_agree,
        "regime_checked": regime_checked,
        "confluence_summary": confluence_summary,
        "strength_bar": strength_bar,
        "example": example,
        "news_title": news_item["title"],
        "news_title_fa": news_title_fa,
        "news_url": news_item["url"],
        "published_at": published_at,
    }


def render_analysis_text(data, settings):
    """بخش «نمایش»: از روی داده‌ی خام compute_analysis_data، متن نهایی رو بر اساس تنظیمات کاربر می‌سازه."""
    tech = data["tech"]
    code = data["code"]
    coin = data["coin"]
    url = data.get("news_url", "")

    header = (
        f"{_invisible_link(url) if url else ''}"
        f"📰 خبر ({coin}): {html_escape(data['news_title_fa'])}\n"
        f"🕒 {format_datetime(data['published_at'], settings)}\n"
        f"{'[کد: ' + code + ']' if code else ''}\n\n"
    )

    if tech.get("no_trade"):
        reason = tech.get("no_trade_reason", "سیگنال کافی واضح نیست")
        return (
            f"{header}"
            f"{direction_label('NEUTRAL')}\n\n"
            f"📊 قیمت فعلی: {tech['price']} | RSI: {tech['rsi']} ({rsi_short_tag(tech['rsi'])})\n"
            f"🧱 نقاط کلیدی بازار: حمایت: {tech['support']} | مقاومت: {tech['resistance']}\n"
            f"📈 رژیم بازار: {_regime_line(data)}\n\n"
            f"{data['confluence_summary']}\n\n"
            f"{data['strength_bar']}\n\n"
            f"⚪ با این‌که این خبر مهم بود، معامله پیشنهاد نمی‌شه — علت: {reason}\n"
            f"برای همین ربات هیچ هدف/استاپ ساختگی پیشنهاد نمی‌ده."
        )

    example_block = ""
    if data["example"]:
        example = data["example"]
        leverage = example["required_leverage"]
        if leverage is not None and leverage <= 1:
            leverage_line = "• اهرم لازم: نیازی نیست (حجم پوزیشن از سرمایه‌ی فرضی کمتره)"
        else:
            leverage_line = f"• اهرم لازم برای این سرمایه‌ی فرضی: ~{leverage}x"

        example_block = (
            f"\n💰 مثال محاسبه (سرمایه فرضی {format_money(EXAMPLE_CAPITAL, settings)}, ریسک {EXAMPLE_RISK_PERCENT}٪):\n"
            f"• مبلغ در ریسک: {format_money(example['risk_amount'], settings)}\n"
            f"• حجم پوزیشن پیشنهادی: ~{format_money(example['position_size'], settings)}\n"
            f"{leverage_line}\n"
            f"(این عدد اهرم، فقط برای همین سرمایه‌ی فرضی {format_money(EXAMPLE_CAPITAL, settings)}ه — "
            f"با سرمایه‌ی واقعی خودت، عدد اهرم طبیعتاً فرق می‌کنه، چون اهرم به نسبت سرمایه به حجم پوزیشن بستگی داره نه به مقدار مطلقش)"
        )

    return (
        f"{header}"
        f"{direction_label(tech['direction'])}\n\n"
        f"📊 تحلیل فنی: RSI={tech['rsi']} ({rsi_short_tag(tech['rsi'])}) | "
        f"قیمت={tech['price']} | ATR={tech['atr']} ({atr_short_tag(tech['atr'], tech['price'])}, تایم‌فریم: {tech['atr_interval_label']})\n"
        f"😨 حس بازار: {data['fg_value']} ({data['fg_label']}) | "
        f"فاندینگ: {data['funding_rate']}٪ ({funding_short_tag(data['funding_rate'])}) | "
        f"تغییر پوزیشن باز (۲۴س): {data['oi_change']}٪\n"
        f"📊 نسبت لانگ/شورت: {data.get('ls_ratio')} ({long_short_short_tag(data.get('ls_ratio'))}) | "
        f"حجم: {data.get('volume_ratio')}× میانگین | "
        f"فاصله از MA۵۰: {data.get('ma_trend_percent')}٪\n"
        f"📐 سطوح معامله: استاپ: {tech['stop_loss']}{' 🧱' if tech.get('sr_used_for_stop') else ''} | R:R = 1:{tech['risk_reward']}\n"
        f"{_laddered_targets_block(tech)}\n"
        f"🧱 نقاط کلیدی بازار: حمایت (Support): {tech['support']} | مقاومت (Resistance): {tech['resistance']}\n"
        f"⏱️ افق زمانی: {tech['time_horizon']}\n\n"
        f"{data['confluence_summary']}\n"
        f"{example_block}\n\n"
        f"{data['strength_bar']}"
    )


def build_daily_digest(settings=None, watchlist=None):
    """
    خلاصه‌ی دوره‌ای — مستقل از خبر، وضعیت فشرده‌ی همه‌ی ارزهای واچ‌لیستِ همون کاربر رو یک‌جا می‌ده.
    برای صبح/شب یا هر زمان‌بندی دیگه‌ای که در main.py تنظیم بشه.
    """
    if settings is None:
        settings = {"calendar": "gregorian", "timezone": "Asia/Tehran", "currency": "USD", "toman_rate": None}
    if not watchlist:
        return None

    from datetime import timezone as _tz
    now = datetime.now(_tz.utc)

    fg_value, fg_label = get_fear_greed_index()
    lines = [f"🗞️ خلاصه‌ی وضعیت بازار — {format_datetime(now, settings)}\n"]
    if fg_value is not None:
        lines.append(f"😨 حس کلی بازار: {fg_value} ({fg_label})\n")

    for coin, symbol in watchlist.items():
        tech = analyze_coin(symbol, period=RSI_PERIOD, interval=KLINES_INTERVAL, interval_label="یک‌ساعته")
        if tech is None:
            continue
        funding_rate = get_funding_rate(symbol)
        summary = build_confluence_summary(tech["rsi"], funding_rate, fg_value)
        # فقط ایموجی نتیجه رو برای خلاصه‌ی فشرده نگه می‌داریم
        status_emoji = summary.split()[0]
        lines.append(
            f"{status_emoji} {coin}: قیمت={tech['price']} | RSI={tech['rsi']} ({rsi_short_tag(tech['rsi'])}) | "
            f"فاندینگ={funding_rate}٪"
        )

    lines.append(
        "\nبرای جزئیات کامل هر ارز، منتظر خبر مرتبطش بمون یا با /watchlist لیست فعلی رو ببین."
    )
    return "\n".join(lines)
