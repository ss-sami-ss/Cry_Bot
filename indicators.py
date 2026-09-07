# -*- coding: utf-8 -*-
"""
محاسبه‌ی اندیکاتورهای فنی از روی داده‌ی قیمتی Binance.
همه‌ی این محاسبات صرفاً ریاضی و بر پایه‌ی داده‌ی عمومی بازارن —
هیچ‌کدوم توصیه یا پیش‌بینی قطعی نیستن، صرفاً معیارهای رایج تحلیل تکنیکال.
"""

import requests

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"


def smart_round(value, reference_price=None):
    """
    گرد کردن هوشمند — به‌جای round(x, 6) ثابت که برای میم‌کوین‌ها (مثل SHIB، PEPE
    که قیمتشون چندتا صفر بعد از اعشار داره) عملاً همه‌ی دقت رو از بین می‌بره،
    تعداد رقم اعشار رو بر اساس اندازه‌ی قیمت تنظیم می‌کنه.
    """
    if value is None:
        return None
    ref = abs(reference_price) if reference_price is not None else abs(value)
    if ref == 0:
        return round(value, 10)

    if ref >= 100:
        decimals = 2
    elif ref >= 1:
        decimals = 4
    elif ref >= 0.01:
        decimals = 6
    elif ref >= 0.0001:
        decimals = 8
    else:
        decimals = 12  # میم‌کوین‌هایی مثل SHIB (~0.000005) یا PEPE (~0.00000001)

    return round(value, decimals)


def get_klines(symbol, interval="1h", limit=100):
    """گرفتن کندل‌های قیمتی از Binance. هر کندل: [open_time, open, high, low, close, volume, ...]"""
    try:
        resp = requests.get(
            BINANCE_KLINES_URL,
            params={"symbol": symbol, "interval": interval, "limit": limit},
            timeout=10,
        )
        resp.raise_for_status()
        raw = resp.json()
        return [
            {
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
            }
            for k in raw
        ]
    except Exception as e:
        print(f"[خطا در گرفتن کندل‌ها] {e}")
        return []


def get_current_price(symbol):
    """قیمت لحظه‌ای یه نماد — برای مقایسه‌ی وضعیت فعلی در پیگیری معامله."""
    try:
        resp = requests.get(
            "https://api.binance.com/api/v3/ticker/price",
            params={"symbol": symbol},
            timeout=10,
        )
        resp.raise_for_status()
        return float(resp.json()["price"])
    except Exception as e:
        print(f"[خطا در گرفتن قیمت لحظه‌ای] {e}")
        return None


def direction_label(direction):
    if direction == "SHORT":
        return "🔽 شورت (Short)"
    if direction == "NEUTRAL":
        return "⚪ سیگنال کافی واضح نیست"
    return "🔼 لانگ (Long)"


def calculate_rsi(closes, period=14):
    """محاسبه‌ی RSI استاندارد."""
    if len(closes) < period + 1:
        return None

    gains, losses = [], []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 1)


def calculate_volume_spike(candles, lookback=20):
    """
    مقایسه‌ی حجم آخرین کندل با میانگین حجم N کندل قبلی.
    برمی‌گردونه: (نسبت_حجم, جهت_کندل) — جهت لازمه که بدونیم جهش حجم صعودیه یا نزولی.
    """
    if not candles or len(candles) < lookback + 1:
        return None, None

    last = candles[-1]
    previous = candles[-(lookback + 1):-1]

    avg_volume = sum(c["volume"] for c in previous) / len(previous)
    if avg_volume == 0:
        return None, None

    volume_ratio = round(last["volume"] / avg_volume, 2)
    direction = "up" if last["close"] >= last["open"] else "down"
    return volume_ratio, direction


def calculate_ma_trend(candles, period=50):
    """درصد فاصله‌ی قیمت فعلی از میانگین متحرک ساده‌ی N دوره‌ای — مثبت یعنی بالای میانگین."""
    if not candles or len(candles) < period:
        return None

    closes = [c["close"] for c in candles[-period:]]
    ma = sum(closes) / len(closes)
    if ma == 0:
        return None

    price = candles[-1]["close"]
    return round((price - ma) / ma * 100, 2)


TREND_EFFICIENCY_THRESHOLD = 0.3  # بالای این یعنی «روند واقعی»، پایینش یعنی «رنج/بی‌جهت»


def calculate_market_regime(candles, lookback=30):
    """
    تشخیص می‌ده بازار الان تو حالت «روند واقعی» (Trending) هست یا «رنج/بی‌جهت» (Ranging)،
    با معیار شناخته‌شده‌ی Kaufman's Efficiency Ratio: نسبت «چقدر قیمت واقعاً جابه‌جا شده»
    به «چقدر مسیر رفته». نزدیک ۱ یعنی مستقیم و قاطع حرکت کرده (روند قوی)،
    نزدیک ۰ یعنی زیاد نوسان کرده ولی جایی نرسیده (رنج).

    چرا این مهمه: تحلیل روی داده‌ی واقعی ۳۰ روزه نشون داد وقتی بازار تو روند واقعیه،
    خیلی از سیگنال‌های «برگشت به میانگین» (RSI بالا و غیره) برعکس عمل می‌کنن —
    باید بدونیم الان تو کدوم حالتیم که تصمیم درست بگیریم.

    برمی‌گردونه: (regime, direction) — regime یکی از "TRENDING"/"RANGING"،
    direction یکی از "UP"/"DOWN"/None (فقط وقتی TRENDING باشه معنی داره)
    """
    if not candles or len(candles) < lookback + 1:
        return "RANGING", None

    window = candles[-lookback:]
    closes = [c["close"] for c in window]

    net_change = closes[-1] - closes[0]
    total_path = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes)))

    if total_path == 0:
        return "RANGING", None

    efficiency_ratio = abs(net_change) / total_path

    if efficiency_ratio >= TREND_EFFICIENCY_THRESHOLD:
        direction = "UP" if net_change > 0 else "DOWN"
        return "TRENDING", direction

    return "RANGING", None


def calculate_multi_timeframe_regime(binance_symbol):
    """
    برای اطمینان بیشتر، رژیم رو هم‌زمان تو ۳ تایم‌فریم (۱ساعته، ۴ساعته، روزانه) چک می‌کنه.
    فقط وقتی همه‌ی تایم‌فریم‌هایی که «روند» تشخیص دادن، **هم‌جهت** هم باشن (همه صعودی
    یا همه نزولی)، نتیجه رو TRENDING اعلام می‌کنه — وگرنه محافظه‌کارانه RANGING برمی‌گردونه.

    برمی‌گردونه: (regime, direction, agreement_count, checked_count)
    agreement_count یعنی چندتا از تایم‌فریم‌های چک‌شده روند هم‌جهت داشتن.
    """
    timeframes = [("1h", 30), ("4h", 30), ("1d", 20)]
    results = []

    for interval, lookback in timeframes:
        candles = get_klines(binance_symbol, interval=interval, limit=max(lookback + 10, 40))
        if not candles:
            continue
        regime, direction = calculate_market_regime(candles, lookback=lookback)
        results.append((interval, regime, direction))

    checked_count = len(results)
    if checked_count == 0:
        return "RANGING", None, 0, 0

    trending = [(interval, direction) for interval, regime, direction in results if regime == "TRENDING"]
    if not trending:
        return "RANGING", None, 0, checked_count

    directions = set(d for _, d in trending)
    if len(directions) == 1:
        return "TRENDING", trending[0][1], len(trending), checked_count

    # تایم‌فریم‌ها روند دارن ولی جهتشون ضدونقیضه (مثلاً کوتاه‌مدت صعودی، بلندمدت نزولی) —
    # محافظه‌کارانه RANGING می‌گیریم، چون سیگنال روشنی نیست.
    return "RANGING", None, 0, checked_count


def calculate_atr(candles, period=14):
    """محاسبه‌ی Average True Range (میانگین دامنه‌ی نوسان)."""
    if len(candles) < period + 1:
        return None

    true_ranges = []
    for i in range(1, len(candles)):
        high = candles[i]["high"]
        low = candles[i]["low"]
        prev_close = candles[i - 1]["close"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_ranges.append(tr)

    atr = sum(true_ranges[-period:]) / period
    reference_price = candles[-1]["close"] if candles else atr
    return smart_round(atr, reference_price)


def interpret_rsi(rsi):
    """
    ترجمه‌ی عدد RSI به یه توضیح قابل‌فهم.
    RSI بین ۰ تا ۱۰۰ نوسان می‌کنه و نشون می‌ده قدرت خرید در برابر فروش
    در چند کندل اخیر چطور بوده — نه پیش‌بینی، بلکه توصیف وضعیت فعلی.
    """
    if rsi is None:
        return "داده کافی برای محاسبه نیست"

    if rsi >= 80:
        return f"{rsi} — بازار به‌شدت اشباع خرید است؛ قیمت خیلی سریع بالا رفته و احتمال اصلاح/توقف رشد در کوتاه‌مدت افزایش یافته"
    elif rsi >= 70:
        return f"{rsi} — بازار وارد ناحیه اشباع خرید شده (روند صعودی بوده، ولی زیاد بالا رفته)؛ احتمال توقف یا اصلاح افزایش یافته"
    elif rsi >= 55:
        return f"{rsi} — بازار تمایل صعودی دارد و هنوز به ناحیه اشباع نرسیده؛ فضا برای رشد بیشتر باقی مانده"
    elif rsi >= 45:
        return f"{rsi} — بازار در حالت خنثی و بدون روند مشخص است"
    elif rsi >= 30:
        return f"{rsi} — بازار تمایل نزولی دارد ولی هنوز اشباع فروش نشده"
    else:
        return f"{rsi} — بازار اشباع فروش است؛ قیمت خیلی سریع پایین رفته و احتمال بازگشت رو به بالا در کوتاه‌مدت افزایش یافته"


def rsi_short_tag(rsi):
    """نسخه‌ی خیلی کوتاه برای استفاده در پیام‌های فشرده."""
    if rsi is None:
        return ""
    if rsi >= 80:
        return "اشباع خرید شدید"
    elif rsi >= 70:
        return "اشباع خرید، احتمال اصلاح"
    elif rsi >= 55:
        return "تمایل صعودی"
    elif rsi >= 45:
        return "خنثی"
    elif rsi >= 30:
        return "تمایل نزولی"
    else:
        return "اشباع فروش، احتمال بازگشت"


# واحد زمانی هر کندل، برای ساختن جمله‌ی "X ساعت/روز گذشته"
_INTERVAL_TIME_UNIT = {
    "پانزده‌دقیقه‌ای": "× ۱۵ دقیقه",
    "یک‌ساعته": "ساعت",
    "چهارساعته": "× ۴ ساعت",
    "روزانه": "روز",
}


def interpret_atr(atr, price, period, interval_label):
    """
    توضیح ATR: هم بازه‌ی زمانی محاسبه (چند کندل، با چه تایم‌فریم)
    و هم کاربردش (معیار میزان نوسان، نه جهت حرکت).
    """
    if atr is None or price == 0:
        return "داده کافی برای محاسبه نیست"

    atr_percent = round(atr / price * 100, 2)
    time_unit = _INTERVAL_TIME_UNIT.get(interval_label, interval_label)

    return (
        f"{atr} (معادل ~{atr_percent}٪ قیمت فعلی) — "
        f"میانگین دامنه‌ی نوسان هر کندل {interval_label} در {period} کندل اخیر "
        f"(یعنی نوسان معمول بازار در طول تقریباً {period} {time_unit} گذشته). "
        f"این عدد نشون‌دهنده‌ی شدت نوسان است، نه جهت حرکت — هرچه بزرگ‌تر، بازار پرتلاطم‌تر و "
        f"معمولاً استاپ‌لاس هم باید فاصله‌ی بیشتری از قیمت داشته باشه تا نوسان عادی باعث خروج زودهنگام نشه."
    )


def atr_short_tag(atr, price):
    """نسخه‌ی کوتاه: فقط درصد نوسان نسبت به قیمت."""
    if atr is None or price == 0:
        return ""
    atr_percent = round(atr / price * 100, 1)
    return f"~{atr_percent}٪ نوسان دوره اخیر"


def find_support_resistance(candles, lookback=50):
    """پیدا کردن ساده‌ی نزدیک‌ترین سقف و کف اخیر (بر پایه‌ی بیشینه/کمینه‌ی بازه)."""
    recent = candles[-lookback:] if len(candles) >= lookback else candles
    if not recent:
        return None, None
    resistance = max(c["high"] for c in recent)
    support = min(c["low"] for c in recent)
    reference_price = recent[-1]["close"]
    return smart_round(support, reference_price), smart_round(resistance, reference_price)


def estimate_time_horizon_hours(candles, price, target_price):
    """
    تخمین عددی (به ساعت) زمان لازم برای رسیدن به تارگت،
    بر پایه‌ی میانگین نوسان کندل‌های ورودی. این فقط عدد خام رو می‌ده؛
    برای متن قابل‌نمایش از estimate_time_horizon استفاده کن.
    """
    if not candles or price == 0:
        return None

    avg_move_percent = (
        sum(abs(c["close"] - c["open"]) / c["open"] for c in candles) / len(candles) * 100
    )
    if avg_move_percent == 0:
        return None

    distance_percent = abs(target_price - price) / price * 100
    return distance_percent / avg_move_percent


def estimate_time_horizon(candles, price, target_price):
    """
    تخمین تقریبی زمان لازم برای رسیدن به تارگت، به‌صورت متن قابل‌نمایش (بازه‌ی کمینه-بیشینه).
    این یه برآورد آماری ساده‌ست، نه پیش‌بینی قطعی.
    """
    est_hours = estimate_time_horizon_hours(candles, price, target_price)
    if est_hours is None:
        return None

    low = max(1, round(est_hours * 0.5))
    high = round(est_hours * 1.5)
    return f"{low} تا {high} ساعت"


# قانون انتخاب تایم‌فریم ATR: با توجه به این‌که افق تخمینی معامله چند ساعته‌ست،
# کدوم تایم‌فریم کندل برای اندازه‌گیری نوسان مناسب‌تره.
# منطق: تایم‌فریم باید به اندازه‌ای ریز باشه که چندین کندل تو افق معامله جا بشه
# (نه خیلی درشت که فقط ۱-۲ کندل رو پوشش بده، نه خیلی ریز که فقط نویز کوتاه‌مدت رو نشون بده).
_ATR_TIMEFRAME_RULES = [
    (3, "15m", "پانزده‌دقیقه‌ای"),
    (30, "1h", "یک‌ساعته"),
    (120, "4h", "چهارساعته"),
]
_ATR_TIMEFRAME_FALLBACK = ("1d", "روزانه")


def pick_atr_interval(estimated_hours):
    """
    بر اساس افق زمانی تخمینی (ساعت)، بهترین تایم‌فریم رو برای محاسبه‌ی ATR انتخاب می‌کنه.
    برمی‌گردونه: (interval_code, interval_label)
    """
    if estimated_hours is None:
        return "1h", "یک‌ساعته"

    for threshold, interval, label in _ATR_TIMEFRAME_RULES:
        if estimated_hours <= threshold:
            return interval, label

    return _ATR_TIMEFRAME_FALLBACK


def build_no_trade_result(base, reason="سیگنال کافی واضح نیست"):
    """
    وقتی سیگنال‌ها به‌قدر کافی هم‌جهت نیستن، یا نسبت ریسک‌به‌ریوارد ذاتاً بد باشه،
    به‌جای پیشنهاد قاطع لانگ/شورت با هدف/استاپ ساختگی، این نتیجه‌ی «خنثی» برگردونده
    می‌شه — فقط اطلاعات پایه، بدون سطوح معامله. علت دقیق تو reason مشخص می‌شه.
    """
    rsi = base["rsi"]
    return {
        "price": base["price"],
        "rsi": rsi,
        "rsi_explanation": interpret_rsi(rsi),
        "direction": "NEUTRAL",
        "atr": None,
        "atr_interval": None,
        "atr_interval_label": None,
        "atr_explanation": "چون سیگنال کافی برای تعیین جهت نبود، ATR برای استاپ محاسبه نشد",
        "support": base["support"],
        "resistance": base["resistance"],
        "stop_loss": None,
        "target": None,
        "target_1": None,
        "target_2": None,
        "target_3": None,
        "target_1_close_pct": None,
        "target_2_close_pct": None,
        "target_3_close_pct": None,
        "risk_reward": None,
        "time_horizon": None,
        "time_horizon_hours": None,
        "sr_used_for_stop": False,
        "no_trade": True,
        "no_trade_reason": reason,
    }


def determine_direction(rsi, price, support, resistance):
    """
    تشخیص جهت پیشنهادی معامله (لانگ یا شورت) — چون تا الان همیشه فقط لانگ در نظر گرفته می‌شد.

    منطق: اگه RSI پایینه (بازار اشباع فروش) → احتمال بازگشت به بالا → لانگ
          اگه RSI بالاست (بازار اشباع خرید) → احتمال اصلاح به پایین → شورت
          حالت خنثی → پیش‌فرض لانگ (چون آمار تاریخی بازار رمزارز کلاً صعودی‌تره)
    """
    if rsi is None:
        return "LONG"
    if rsi >= 60:
        return "SHORT"
    if rsi <= 40:
        return "LONG"
    return "LONG"


def get_base_technicals(binance_symbol, period=14, interval="1h"):
    """
    مرحله‌ی اول: فقط داده‌های پایه (قیمت، RSI، حمایت/مقاومت) — بدون تصمیم جهت.
    چون جهت نهایی باید با فاندینگ و Fear&Greed هم ترکیب بشه (که این تابع بهشون
    دسترسی نداره)، تصمیم جهت به لایه‌ی بالاتر (news.py) واگذار می‌شه.
    """
    base_candles = get_klines(binance_symbol, interval=interval, limit=100)
    if not base_candles:
        return None

    closes = [c["close"] for c in base_candles]
    price = closes[-1]
    rsi = calculate_rsi(closes, period=period)
    support, resistance = find_support_resistance(base_candles, lookback=50)
    volume_ratio, volume_direction = calculate_volume_spike(base_candles, lookback=20)
    ma_trend_percent = calculate_ma_trend(base_candles, period=50)

    return {
        "base_candles": base_candles,
        "price": price,
        "rsi": rsi,
        "support": support,
        "resistance": resistance,
        "volume_ratio": volume_ratio,
        "volume_direction": volume_direction,
        "ma_trend_percent": ma_trend_percent,
    }


def finalize_trade_setup(binance_symbol, base, direction, period=14, interval="1h", interval_label="یک‌ساعته"):
    """
    مرحله‌ی دوم: با جهت نهایی (که از ترکیب RSI+فاندینگ+Fear&Greed تعیین شده)،
    هدف/استاپ/تایم‌فریم ATR/افق زمانی رو حساب می‌کنه.
    """
    base_candles = base["base_candles"]
    price = base["price"]
    rsi = base["rsi"]
    support = base["support"]
    resistance = base["resistance"]

    if direction == "SHORT":
        target = support if support and support < price else smart_round(price * 0.97, price)
    else:
        target = resistance if resistance and resistance > price else smart_round(price * 1.03, price)

    # تخمین اولیه‌ی افق زمانی (بر پایه‌ی همون کندل‌های ۱ ساعته)
    est_hours = estimate_time_horizon_hours(base_candles, price, target)
    chosen_interval, chosen_label = pick_atr_interval(est_hours)

    # اگه تایم‌فریم انتخاب‌شده با تایم‌فریم پایه فرق داره، کندل‌های جدید می‌گیریم
    if chosen_interval != interval:
        atr_candles = get_klines(binance_symbol, interval=chosen_interval, limit=100)
        if not atr_candles:
            atr_candles = base_candles
            chosen_interval, chosen_label = interval, interval_label
    else:
        atr_candles = base_candles

    atr = calculate_atr(atr_candles, period=period)

    # استاپ پایه بر اساس ATR (فال‌بک، وقتی سطح حمایت/مقاومت مناسبی در دسترس نباشه)
    if direction == "SHORT":
        atr_stop = smart_round(price + (1.5 * atr), price) if atr else None
    else:
        atr_stop = smart_round(price - (1.5 * atr), price) if atr else None

    # اصل معامله‌گری: وقتی یه سطح حمایت/مقاومتِ روشن و نه‌چندان‌دور وجود داره، اون سطح
    # (نه یه ضریب ثابت از ATR) باید مبنای استاپ باشه — چون شکستن همون سطح دقیقاً
    # نقطه‌ایه که تحلیل رو باطل می‌کنه. ATR فقط وقتی فال‌بک می‌شه که سطح مناسبی نباشه
    # یا خیلی دور باشه (که استاپ غیرمنطقی گشاد نشه).
    SR_MAX_DISTANCE_PERCENT = 0.05  # سطح باید حداکثر ۵٪ با قیمت فاصله داشته باشه که "نزدیک" حساب بشه
    stop_loss = atr_stop
    sr_used_for_stop = False

    if atr:
        buffer = 0.3 * atr
        if direction == "SHORT" and resistance and resistance > price:
            distance_percent = (resistance - price) / price
            if distance_percent <= SR_MAX_DISTANCE_PERCENT:
                stop_loss = smart_round(resistance + buffer, price)
                sr_used_for_stop = True

        elif direction == "LONG" and support and support < price:
            distance_percent = (price - support) / price
            if distance_percent <= SR_MAX_DISTANCE_PERCENT:
                stop_loss = smart_round(support - buffer, price)
                sr_used_for_stop = True

    time_horizon = estimate_time_horizon(base_candles, price, target) if target else None

    risk_reward = None
    if stop_loss and target and (price - stop_loss) != 0:
        risk_reward = round(abs(target - price) / abs(price - stop_loss), 2)

    # هدف‌های پله‌ای (Laddered Take-Profit): به‌جای یه هدف تکی، ۳ تا سطح با
    # فاصله‌ی متفاوت — نزدیک (احتمال بالا)، اصلی (همون هدف حساب‌شده از حمایت/مقاومت)،
    # و دور (نسبت طلایی ۱.۶۱۸ - رایج‌ترین نسبت گسترش تو تحلیل تکنیکال).
    # درصدهای پیشنهادی برای بستن پوزیشن: ۴۰٪ رو هدف ۱، ۳۵٪ رو هدف ۲، ۲۵٪ رو هدف ۳.
    target_1 = target_2 = target_3 = None
    if target:
        distance = abs(target - price)
        if direction == "SHORT":
            target_1 = smart_round(price - 0.5 * distance, price)
            target_3 = smart_round(price - 1.618 * distance, price)
        else:
            target_1 = smart_round(price + 0.5 * distance, price)
            target_3 = smart_round(price + 1.618 * distance, price)
        target_2 = target

    return {
        "price": price,
        "rsi": rsi,
        "rsi_explanation": interpret_rsi(rsi),
        "direction": direction,
        "atr": atr,
        "atr_interval": chosen_interval,
        "atr_interval_label": chosen_label,
        "atr_explanation": interpret_atr(atr, price, period, chosen_label),
        "support": support,
        "resistance": resistance,
        "stop_loss": stop_loss,
        "target": target,
        "target_1": target_1,
        "target_2": target_2,
        "target_3": target_3,
        "target_1_close_pct": 40,
        "target_2_close_pct": 35,
        "target_3_close_pct": 25,
        "risk_reward": risk_reward,
        "time_horizon": time_horizon,
        "time_horizon_hours": est_hours,
        "sr_used_for_stop": sr_used_for_stop,
    }


def analyze_coin(binance_symbol, period=14, interval="1h", interval_label="یک‌ساعته"):
    """
    نسخه‌ی ساده (بدون ترکیب فاندینگ/Fear&Greed) — فقط برای جاهایی که نیازی به
    اون سطح دقت جهت‌یابی نیست (مثلاً خلاصه‌ی دوره‌ای). جهت رو فقط با RSI تعیین می‌کنه.
    برای تحلیل کامل خبر، به‌جاش از get_base_technicals + finalize_trade_setup
    (با جهت تعیین‌شده توسط confluence.decide_direction_and_alignment) استفاده کن.
    """
    base = get_base_technicals(binance_symbol, period=period, interval=interval)
    if base is None:
        return None
    direction = determine_direction(base["rsi"], base["price"], base["support"], base["resistance"])
    return finalize_trade_setup(binance_symbol, base, direction, period=period, interval=interval, interval_label=interval_label)
