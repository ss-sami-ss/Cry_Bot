# -*- coding: utf-8 -*-
"""
تکنیک‌های تحلیلی اضافی — هرکدوم یه روش شناخته‌شده و مستند تحلیل تکنیکاله.
این‌ها مکمل تحلیل اصلی‌ان، نه جایگزینش.

فقط ۳ تکنیک اول با داده‌ی کندل معمولی (OHLCV از Binance) قابل پیاده‌سازیِ
درست و قابل‌اعتماد بودن؛ بقیه (مثل Volume Profile واقعی یا تشخیص سفارش‌های
نهنگ‌ها) نیاز به داده‌ی عمقی بازار (order book / تیک‌به‌تیک) دارن که Binance
رایگان نمی‌ده — برای همین فعلاً کنار گذاشته شدن تا داده‌ی قابل‌اعتماد پیدا بشه.
"""

from indicators import get_klines, calculate_rsi, get_current_price


TECHNIQUES = {
    "round_number": "🔢 عدد رند (Round Number)",
    "multi_timeframe": "📊 هم‌جهتی چند تایم‌فریم (Multi-Timeframe)",
    "break_retest": "🔁 شکست و تست مجدد (Break & Retest)",
}


def analyze_round_number(binance_symbol):
    """
    آیا قیمت فعلی نزدیک یه عدد رند روانی‌ـه؟ (مثلاً ۷۰,۰۰۰ برای بیت‌کوین)
    این نوع اعداد به‌خاطر روانشناسی جمعی، خودشون تبدیل به حمایت/مقاومت می‌شن.
    نیازی به سرمایه/ریسک نداره — فقط یه ارزیابی کیفیه.
    """
    price = get_current_price(binance_symbol)
    if price is None:
        return {"ok": False, "message": "نشد قیمت فعلی رو بگیرم."}

    # مقیاس رندی رو بر اساس اندازه‌ی قیمت تعیین می‌کنیم (برای BTC هزارتایی، برای آلت‌کوین‌های ارزون کوچیک‌تر)
    import math
    magnitude = 10 ** (len(str(int(price))) - 2) if price >= 1 else 0.01
    nearest_round = round(price / magnitude) * magnitude
    distance_percent = abs(price - nearest_round) / price * 100

    is_close = distance_percent <= 0.5

    if is_close:
        message = (
            f"قیمت فعلی ({price}) خیلی نزدیک یه عدد رند روانیه (~{nearest_round}).\n"
            f"فاصله فقط {distance_percent:.2f}٪ — این سطح می‌تونه به‌عنوان یه حمایت/مقاومت "
            f"روانی عمل کنه، چون خیلی از معامله‌گرها ناخودآگاه سفارش‌هاشون رو دور همین اعداد می‌ذارن."
        )
    else:
        message = (
            f"قیمت فعلی ({price}) به عدد رند نزدیکی ({nearest_round}) نیست "
            f"(فاصله {distance_percent:.2f}٪) — این تکنیک فعلاً سیگنال خاصی نمی‌ده."
        )

    return {"ok": True, "favorable": is_close, "message": message, "price": price, "nearest_round": nearest_round}


def analyze_multi_timeframe(binance_symbol):
    """
    RSI رو تو ۳ تایم‌فریم مختلف (۱ساعته، ۴ساعته، روزانه) چک می‌کنه.
    اگه هر سه هم‌جهت باشن (همه صعودی یا همه نزولی)، اعتماد به روند بیشتره.
    نیازی به سرمایه/ریسک نداره.
    """
    intervals = [("1h", "یک‌ساعته"), ("4h", "چهارساعته"), ("1d", "روزانه")]
    results = []

    for interval, label in intervals:
        candles = get_klines(binance_symbol, interval=interval, limit=50)
        if not candles:
            continue
        closes = [c["close"] for c in candles]
        rsi = calculate_rsi(closes, period=14)
        if rsi is None:
            continue
        bias = "صعودی" if rsi >= 55 else ("نزولی" if rsi <= 45 else "خنثی")
        results.append((label, rsi, bias))

    if len(results) < 3:
        return {"ok": False, "message": "نشد داده‌ی کافی برای هر ۳ تایم‌فریم بگیرم."}

    biases = [b for _, _, b in results]
    all_same = len(set(biases)) == 1 and biases[0] != "خنثی"

    lines = [f"{label}: RSI={rsi:.1f} ({bias})" for label, rsi, bias in results]
    detail = "\n".join(lines)

    if all_same:
        message = f"هر ۳ تایم‌فریم هم‌جهت‌ان ({biases[0]}) — این یه سیگنال قوی‌تره:\n{detail}"
    else:
        message = f"تایم‌فریم‌ها هم‌جهت نیستن (یعنی روند هنوز قطعی نیست):\n{detail}"

    return {"ok": True, "favorable": all_same, "message": message}


def analyze_break_retest(binance_symbol):
    """
    آیا قیمت اخیراً از یه سطح حمایت/مقاومت رد شده و الان داره برمی‌گرده برای تست دوباره‌ش؟
    این الگو (Break & Retest) معمولاً قابل‌اعتمادتر از ورود فوری موقع شکسته که.
    نیازی به سرمایه/ریسک نداره.
    """
    from indicators import find_support_resistance

    candles = get_klines(binance_symbol, interval="1h", limit=100)
    if not candles:
        return {"ok": False, "message": "نشد کندل‌ها رو بگیرم."}

    # سطح رو از ۵۰ کندل قبل‌تر از ۱۰ کندل آخر حساب می‌کنیم (که خودِ شکست اخیر روش اثر نذاشته باشه)
    older_candles = candles[:-10]
    support, resistance = find_support_resistance(older_candles, lookback=50)

    recent_candles = candles[-10:]
    current_price = recent_candles[-1]["close"]

    broke_resistance = resistance and any(c["high"] > resistance for c in recent_candles[:-2])
    now_near_resistance = resistance and abs(current_price - resistance) / current_price <= 0.01

    broke_support = support and any(c["low"] < support for c in recent_candles[:-2])
    now_near_support = support and abs(current_price - support) / current_price <= 0.01

    if broke_resistance and now_near_resistance and current_price >= resistance:
        return {
            "ok": True, "favorable": True,
            "message": f"قیمت اخیراً مقاومت ({resistance}) رو شکسته و الان داره از بالا تستش می‌کنه — "
                       f"الگوی Break & Retest صعودی، نسبتاً معتبر.",
        }
    if broke_support and now_near_support and current_price <= support:
        return {
            "ok": True, "favorable": True,
            "message": f"قیمت اخیراً حمایت ({support}) رو شکسته و الان داره از پایین تستش می‌کنه — "
                       f"الگوی Break & Retest نزولی، نسبتاً معتبر.",
        }

    return {
        "ok": True, "favorable": False,
        "message": f"در حال حاضر الگوی شکست-و-تست‌مجدد واضحی دیده نمی‌شه "
                   f"(حمایت اخیر: {support}, مقاومت اخیر: {resistance}, قیمت فعلی: {current_price}).",
    }


ANALYZERS = {
    "round_number": analyze_round_number,
    "multi_timeframe": analyze_multi_timeframe,
    "break_retest": analyze_break_retest,
}


# ============================================================
# نسخه‌ی «سیگنال جهت‌دار» همین ۳ تکنیک — برای دخیل کردنشون تو سیستم
# تصمیم‌گیری اصلی (confluence)، نه فقط منوی دستی. خروجی یه tuple
# (kind, label) سازگار با بقیه‌ی سیگنال‌هاست: kind یا "overheated"
# (شورت‌محور) یا "cooled" (لانگ‌محور)، یا None اگه سیگنال خاصی نبود.
# ============================================================

def round_number_signal(binance_symbol):
    """نزدیکی به عدد رند: اگه قیمت از پایین بهش نزدیک شده (هنوز رد نکرده) → احتمال مقاومت (شورت‌محور).
    اگه از بالاش قرار داره (رد کرده، حالا حمایته) → لانگ‌محور."""
    result = analyze_round_number(binance_symbol)
    if not result.get("ok") or not result.get("favorable"):
        return None

    price = result["price"]
    nearest_round = result.get("nearest_round")
    if nearest_round is None:
        return None

    if price < nearest_round:
        return ("overheated", f"نزدیک عدد رند {nearest_round} از پایین (احتمال مقاومت)")
    else:
        return ("cooled", f"نزدیک عدد رند {nearest_round} از بالا (احتمال حمایت)")


def multi_timeframe_signal(binance_symbol):
    """اگه هر ۳ تایم‌فریم هم‌جهت باشن، جهتشون رو به‌عنوان سیگنال برمی‌گردونه."""
    result = analyze_multi_timeframe(binance_symbol)
    if not result.get("ok") or not result.get("favorable"):
        return None

    if "صعودی" in result["message"]:
        return ("cooled", "هر ۳ تایم‌فریم صعودی‌ان")
    if "نزولی" in result["message"]:
        return ("overheated", "هر ۳ تایم‌فریم نزولی‌ان")
    return None


def break_retest_signal(binance_symbol):
    """الگوی شکست-و-تست‌مجدد، اگه پیدا بشه، جهتش رو برمی‌گردونه."""
    result = analyze_break_retest(binance_symbol)
    if not result.get("ok") or not result.get("favorable"):
        return None

    if "صعودی" in result["message"]:
        return ("cooled", "الگوی شکست-و-تست‌مجدد صعودی")
    if "نزولی" in result["message"]:
        return ("overheated", "الگوی شکست-و-تست‌مجدد نزولی")
    return None


def get_technique_signals(binance_symbol):
    """هر ۳ تکنیک رو اجرا می‌کنه و لیست ۳تایی (هرکدوم یا tuple یا None) برمی‌گردونه."""
    return [
        round_number_signal(binance_symbol),
        multi_timeframe_signal(binance_symbol),
        break_retest_signal(binance_symbol),
    ]
