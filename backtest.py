# -*- coding: utf-8 -*-
"""
اسکریپت بک‌تست — روی کامپیوتر خودت اجرا کن (نه رو سرور ربات، چون نیازی به توکن نداره).

برای ۳ ارز، هرکدوم ۵ سناریو از ۴۸ ساعت اخیر می‌سازه: با داده‌ای که «تا همون لحظه»
در دسترس بوده (نه داده‌ی آینده)، پیش‌بینی می‌سازه، بعد با چیزی که واقعاً اتفاق افتاده
مقایسه می‌کنه. خروجی: هم یه جدول تو کنسول، هم یه فایل CSV.

اجرا:
    pip install requests
    python3 backtest.py
"""

import csv
import sys
import time
from datetime import datetime, timezone

import requests

sys.path.insert(0, ".")
from indicators import (
    calculate_rsi, calculate_atr, find_support_resistance,
    calculate_volume_spike, calculate_ma_trend, smart_round, calculate_market_regime,
)
from confluence import decide_direction_and_alignment
from config import ESTIMATED_ROUNDTRIP_FEE_PERCENT

MIN_ALIGNED_SIGNALS = 3  # هماهنگ با همون قانونی که تازه به خود ربات اضافه شد (عدد خام، نه نسبت)

# ارزهای متنوع‌تر — از بزرگ‌ها تا میم‌کوین‌های پرنوسان
COINS = ["BTC", "ETH", "XRP", "SOL", "DOGE", "SHIB", "PEPE", "ADA", "BNB"]
HOURS_AGO_LIST = list(range(10, 191, 10))  # نمونه‌ی بزرگ‌تر: ۱۹ سناریو به‌جای ۸ برای هر ارز (تا ۱۹۰ ساعت/~۸ روز پیش)

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
BINANCE_FUNDING_HIST_URL = "https://fapi.binance.com/fapi/v1/fundingRate"
BINANCE_OI_HIST_URL = "https://fapi.binance.com/futures/data/openInterestHist"
BINANCE_LS_RATIO_URL = "https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
FEAR_GREED_URL = "https://api.alternative.me/fng/"


def fetch_klines_with_time(symbol, interval="1h", limit=200):
    """کندل‌ها رو با زمان دقیق هر کندل (open_time) برمی‌گردونه — لازم برای بک‌تست."""
    resp = requests.get(BINANCE_KLINES_URL, params={"symbol": symbol, "interval": interval, "limit": limit}, timeout=15)
    resp.raise_for_status()
    raw = resp.json()
    return [
        {
            "open_time": int(k[0]),
            "open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
            "close": float(k[4]), "volume": float(k[5]),
        }
        for k in raw
    ]


def fetch_historical_funding(symbol, at_time_ms):
    """نزدیک‌ترین نرخ فاندینگ قبل از at_time_ms."""
    try:
        resp = requests.get(
            BINANCE_FUNDING_HIST_URL,
            params={"symbol": symbol, "endTime": at_time_ms, "limit": 1},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return None
        return round(float(data[-1]["fundingRate"]) * 100, 4)
    except Exception as e:
        print(f"  [هشدار] فاندینگ تاریخی نگرفت: {e}")
        return None


def fetch_historical_oi_change(symbol, at_time_ms, hours=24):
    try:
        start = at_time_ms - hours * 3600 * 1000
        resp = requests.get(
            BINANCE_OI_HIST_URL,
            params={"symbol": symbol, "period": "1h", "startTime": start, "endTime": at_time_ms, "limit": 30},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if len(data) < 2:
            return None
        old_oi = float(data[0]["sumOpenInterest"])
        new_oi = float(data[-1]["sumOpenInterest"])
        if old_oi == 0:
            return None
        return round((new_oi - old_oi) / old_oi * 100, 2)
    except Exception as e:
        print(f"  [هشدار] OI تاریخی نگرفت: {e}")
        return None


def fetch_historical_ls_ratio(symbol, at_time_ms):
    try:
        start = at_time_ms - 3600 * 1000
        resp = requests.get(
            BINANCE_LS_RATIO_URL,
            params={"symbol": symbol, "period": "1h", "startTime": start, "endTime": at_time_ms, "limit": 1},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return None
        return round(float(data[-1]["longShortRatio"]), 3)
    except Exception as e:
        print(f"  [هشدار] لانگ/شورت تاریخی نگرفت: {e}")
        return None


_fg_cache = None


def fetch_historical_fear_greed(at_time_ms):
    """شاخص ترس‌وطمع روزانه‌ست، پس نزدیک‌ترین روز رو برمی‌گردونیم."""
    global _fg_cache
    try:
        if _fg_cache is None:
            resp = requests.get(FEAR_GREED_URL, params={"limit": 10}, timeout=15)
            resp.raise_for_status()
            _fg_cache = resp.json().get("data", [])

        target_ts = at_time_ms / 1000
        best = min(_fg_cache, key=lambda d: abs(int(d["timestamp"]) - target_ts))
        return int(best["value"])
    except Exception as e:
        print(f"  [هشدار] Fear&Greed تاریخی نگرفت: {e}")
        return None


# ============================================================
# نسخه‌ی تاریخی ۳ تکنیک — چون توابع اصلی techniques.py قیمت/کندل
# «الان» رو می‌گیرن، برای بک‌تست نسخه‌ی مخصوص خودمون رو می‌سازیم که
# فقط از داده‌ی «تا همون لحظه» استفاده کنه.
# ============================================================

def round_number_signal_historical(price):
    magnitude = 10 ** (len(str(int(price))) - 2) if price >= 1 else 0.01
    nearest_round = round(price / magnitude) * magnitude
    distance_percent = abs(price - nearest_round) / price * 100
    if distance_percent > 0.5:
        return None
    if price < nearest_round:
        return ("overheated", f"نزدیک عدد رند {nearest_round} از پایین")
    return ("cooled", f"نزدیک عدد رند {nearest_round} از بالا")


def multi_timeframe_signal_historical(symbol, at_time_ms):
    """RSI رو تو ۱ساعته/۴ساعته/روزانه، همه ختم به همون at_time_ms، چک می‌کنه."""
    biases = []
    for interval in ["1h", "4h", "1d"]:
        try:
            resp = requests.get(
                BINANCE_KLINES_URL,
                params={"symbol": symbol, "interval": interval, "endTime": at_time_ms, "limit": 50},
                timeout=15,
            )
            resp.raise_for_status()
            raw = resp.json()
            if len(raw) < 20:
                continue
            closes = [float(k[4]) for k in raw]
            rsi = calculate_rsi(closes, period=14)
            if rsi is None:
                continue
            biases.append("up" if rsi >= 55 else ("down" if rsi <= 45 else "neutral"))
        except Exception:
            continue

    if len(biases) < 3:
        return None
    if all(b == "up" for b in biases):
        return ("cooled", "هر ۳ تایم‌فریم صعودی‌ان")
    if all(b == "down" for b in biases):
        return ("overheated", "هر ۳ تایم‌فریم نزولی‌ان")
    return None


def multi_timeframe_regime_historical(symbol, at_time_ms, base_window_1h):
    """
    نسخه‌ی تاریخی calculate_multi_timeframe_regime — دقیقاً همون منطق ربات زنده،
    ولی با کندل‌های «تا همون لحظه» (نه الان). قبلاً بک‌تست فقط از ۱ساعته استفاده
    می‌کرد که با ربات زنده (که ۳ تایم‌فریم رو چک می‌کنه) هماهنگ نبود.
    """
    results = [calculate_market_regime(base_window_1h, lookback=30)]

    for interval, lookback in [("4h", 30), ("1d", 20)]:
        try:
            resp = requests.get(
                BINANCE_KLINES_URL,
                params={"symbol": symbol, "interval": interval, "endTime": at_time_ms, "limit": max(lookback + 10, 40)},
                timeout=15,
            )
            resp.raise_for_status()
            raw = resp.json()
            if len(raw) < lookback + 1:
                continue
            candles = [{"close": float(k[4])} for k in raw]
            results.append(calculate_market_regime(candles, lookback=lookback))
        except Exception:
            continue

    trending = [(regime, direction) for regime, direction in results if regime == "TRENDING"]
    if not trending:
        return "RANGING", None

    directions = set(d for _, d in trending)
    if len(directions) == 1:
        return "TRENDING", trending[0][1]

    return "RANGING", None


def break_retest_signal_historical(base_window):
    """از همون کندل‌های محدود به گذشته که برای بقیه‌ی تحلیل هم استفاده شده."""
    if len(base_window) < 60:
        return None

    older = base_window[:-10]
    support, resistance = find_support_resistance(older, lookback=50)
    recent = base_window[-10:]
    current_price = recent[-1]["close"]

    broke_resistance = resistance and any(c["high"] > resistance for c in recent[:-2])
    now_near_resistance = resistance and abs(current_price - resistance) / current_price <= 0.01
    broke_support = support and any(c["low"] < support for c in recent[:-2])
    now_near_support = support and abs(current_price - support) / current_price <= 0.01

    if broke_resistance and now_near_resistance and current_price >= resistance:
        return ("cooled", "الگوی شکست-و-تست‌مجدد صعودی")
    if broke_support and now_near_support and current_price <= support:
        return ("overheated", "الگوی شکست-و-تست‌مجدد نزولی")
    return None


def analyze_at_point(symbol, candles, scenario_index):
    """دقیقاً همون منطق ربات، ولی با داده‌ی محدود به «تا همون لحظه» (بدون نگاه به آینده)."""
    # نکته‌ی مهم: base_window باید خودِ کندل scenario_index رو هم شامل بشه (نه فقط قبلش) —
    # وگرنه قیمت ورود از یه کندل قبل‌تر گرفته می‌شه ولی چک نتیجه از scenario_index+1 شروع
    # می‌شه، و خودِ کندل scenario_index هیچ‌وقت برای هدف/استاپ بررسی نمی‌شه (باگِ آف‌بای‌وان).
    base_window = candles[max(0, scenario_index - 99):scenario_index + 1]
    if len(base_window) < 30:
        return None

    closes = [c["close"] for c in base_window]
    price = closes[-1]
    rsi = calculate_rsi(closes, period=14)
    support, resistance = find_support_resistance(base_window, lookback=50)
    volume_ratio, volume_direction = calculate_volume_spike(base_window, lookback=20)
    ma_trend_percent = calculate_ma_trend(base_window, period=50)
    atr = calculate_atr(base_window, period=14)

    at_time_ms = candles[scenario_index]["open_time"]
    funding_rate = fetch_historical_funding(symbol, at_time_ms)
    oi_change = fetch_historical_oi_change(symbol, at_time_ms)
    ls_ratio = fetch_historical_ls_ratio(symbol, at_time_ms)
    fg_value = fetch_historical_fear_greed(at_time_ms)

    technique_flags = [
        round_number_signal_historical(price),
        multi_timeframe_signal_historical(symbol, at_time_ms),
        break_retest_signal_historical(base_window),
    ]

    # رژیم بازار — چندتایم‌فریمی، دقیقاً هماهنگ با ربات زنده (نه فقط ۱ساعته)
    regime, trend_direction = multi_timeframe_regime_historical(symbol, at_time_ms, base_window)

    direction, aligned, total = decide_direction_and_alignment(
        rsi, funding_rate, fg_value, price, support, resistance,
        oi_change, ls_ratio, volume_ratio, volume_direction, ma_trend_percent,
        technique_flags, regime, trend_direction,
    )

    no_trade = aligned < MIN_ALIGNED_SIGNALS

    target = target_1 = target_2 = target_3 = stop = None
    sr_used_for_stop = False

    if not no_trade:
        # هدف اصلی (target_2) — دقیقاً همون منطق ربات
        if direction == "SHORT":
            target = support if support and support < price else smart_round(price * 0.97, price)
        else:
            target = resistance if resistance and resistance > price else smart_round(price * 1.03, price)

        # استاپ — دقیقاً همون منطق ربات: اول ATR، ولی اگه سطح S/R نزدیک (حداکثر ۵٪) بود، اون اولویت داره
        atr_stop = None
        if atr:
            if direction == "SHORT":
                atr_stop = smart_round(price + 1.5 * atr, price)
            else:
                atr_stop = smart_round(price - 1.5 * atr, price)

        stop = atr_stop
        SR_MAX_DISTANCE_PERCENT = 0.05
        if atr:
            buffer = 0.3 * atr
            if direction == "SHORT" and resistance and resistance > price:
                distance_percent = (resistance - price) / price
                if distance_percent <= SR_MAX_DISTANCE_PERCENT:
                    stop = smart_round(resistance + buffer, price)
                    sr_used_for_stop = True
            elif direction == "LONG" and support and support < price:
                distance_percent = (price - support) / price
                if distance_percent <= SR_MAX_DISTANCE_PERCENT:
                    stop = smart_round(support - buffer, price)
                    sr_used_for_stop = True

        # هدف‌های پله‌ای — دقیقاً همون فرمول ربات (۰.۵x / ۱x / ۱.۶۱۸x فاصله)
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
        "time": datetime.fromtimestamp(at_time_ms / 1000, tz=timezone.utc),
        "price": price, "rsi": rsi, "direction": direction,
        "aligned": aligned, "total": total, "no_trade": no_trade,
        "regime": regime, "trend_direction": trend_direction,
        "target": target, "stop": stop, "sr_used_for_stop": sr_used_for_stop,
        "target_1": target_1, "target_2": target_2, "target_3": target_3,
        "funding_rate": funding_rate, "oi_change": oi_change,
        "ls_ratio": ls_ratio, "fg_value": fg_value,
    }


def check_actual_outcome(candles, scenario_index, prediction):
    """
    شبیه‌سازی پله‌ای: ۴۰٪ پوزیشن رو هدف ۱، ۳۵٪ رو هدف ۲، ۲۵٪ رو هدف ۳ می‌بندیم.
    بعد از رسیدن به هدف ۱، استاپ رو می‌بریم رو نقطه‌ی ورود (Break-even) — یعنی
    از اون لحظه به بعد، بدترین حالت برای بخش باقی‌مونده، سود صفره، نه ضرر.
    """
    if prediction.get("no_trade"):
        return "⚪ بدون معامله (سیگنال ناکافی)", None, None

    future_candles = candles[scenario_index + 1:]
    if not future_candles:
        return "بدون داده‌ی بعدی", None, None

    direction = prediction["direction"]
    entry = prediction["price"]
    stop = prediction["stop"]
    t1, t2, t3 = prediction.get("target_1"), prediction.get("target_2"), prediction.get("target_3")

    if not (t1 and t2 and t3 and stop):
        # فال‌بک به هدف تکی قدیمی، اگه به هر دلیلی پله‌ای ساخته نشده بود
        target = prediction.get("target")
        for c in future_candles:
            if direction == "SHORT":
                if target and c["low"] <= target:
                    return "🎯 هدف خورد", target, round((entry - target) / entry * 100 - ESTIMATED_ROUNDTRIP_FEE_PERCENT, 2)
                if stop and c["high"] >= stop:
                    return "🛑 استاپ خورد", stop, round((entry - stop) / entry * 100 - ESTIMATED_ROUNDTRIP_FEE_PERCENT, 2)
            else:
                if target and c["high"] >= target:
                    return "🎯 هدف خورد", target, round((target - entry) / entry * 100 - ESTIMATED_ROUNDTRIP_FEE_PERCENT, 2)
                if stop and c["low"] <= stop:
                    return "🛑 استاپ خورد", stop, round((stop - entry) / entry * 100 - ESTIMATED_ROUNDTRIP_FEE_PERCENT, 2)
        current = future_candles[-1]["close"]
        pnl = round((entry - current) / entry * 100, 2) if direction == "SHORT" else round((current - entry) / entry * 100, 2)
        return "⏳ هنوز باز", current, round(pnl - ESTIMATED_ROUNDTRIP_FEE_PERCENT, 2)

    # --- شبیه‌سازی پله‌ای واقعی (تریلینگ‌استاپ ۳مرحله‌ای) ---
    weights = {"t1": 0.40, "t2": 0.35, "t3": 0.25}
    closed_pct = 0.0
    weighted_pnl = 0.0
    current_stop = stop
    t1_hit = False
    t2_hit = False
    outcome_label = "⏳ هنوز باز"
    last_price = entry

    def stop_note():
        if t2_hit:
            return " (بعد از هدف۲، رو هدف۱)"
        if t1_hit:
            return " (بعد از هدف۱، سربه‌سر)"
        return ""

    for c in future_candles:
        if direction == "SHORT":
            # اول چک کن استاپ (پله‌ای‌شده) خورده یا نه
            if closed_pct < 1.0 and c["high"] >= current_stop:
                remaining = 1.0 - closed_pct
                stop_pnl = (entry - current_stop) / entry * 100
                weighted_pnl += remaining * stop_pnl
                closed_pct = 1.0
                outcome_label = "🛑 استاپ خورد" + stop_note()
                break
            if not t1_hit and c["low"] <= t1:
                weighted_pnl += weights["t1"] * ((entry - t1) / entry * 100)
                closed_pct += weights["t1"]
                current_stop = entry  # پله ۱: ببر رو نقطه‌ی ورود (سربه‌سر)
                t1_hit = True
            if t1_hit and not t2_hit and closed_pct < weights["t1"] + weights["t2"] and c["low"] <= t2:
                weighted_pnl += weights["t2"] * ((entry - t2) / entry * 100)
                closed_pct += weights["t2"]
                current_stop = t1  # پله ۲: ببر رو هدف۱ — سود همون سطح قفل می‌شه
                t2_hit = True
            if closed_pct >= weights["t1"] + weights["t2"] and c["low"] <= t3:
                weighted_pnl += weights["t3"] * ((entry - t3) / entry * 100)
                closed_pct = 1.0
                outcome_label = "🎯 هر ۳ هدف خورد"
                break
        else:
            if closed_pct < 1.0 and c["low"] <= current_stop:
                remaining = 1.0 - closed_pct
                stop_pnl = (current_stop - entry) / entry * 100
                weighted_pnl += remaining * stop_pnl
                closed_pct = 1.0
                outcome_label = "🛑 استاپ خورد" + stop_note()
                break
            if not t1_hit and c["high"] >= t1:
                weighted_pnl += weights["t1"] * ((t1 - entry) / entry * 100)
                closed_pct += weights["t1"]
                current_stop = entry
                t1_hit = True
            if t1_hit and not t2_hit and closed_pct < weights["t1"] + weights["t2"] and c["high"] >= t2:
                weighted_pnl += weights["t2"] * ((t2 - entry) / entry * 100)
                closed_pct += weights["t2"]
                current_stop = t1
                t2_hit = True
            if closed_pct >= weights["t1"] + weights["t2"] and c["high"] >= t3:
                weighted_pnl += weights["t3"] * ((t3 - entry) / entry * 100)
                closed_pct = 1.0
                outcome_label = "🎯 هر ۳ هدف خورد"
                break
        last_price = c["close"]

    if closed_pct < 1.0:
        # هنوز باز — بخش بسته‌نشده رو با قیمت فعلی حساب می‌کنیم (فرضی)
        remaining = 1.0 - closed_pct
        open_pnl = (entry - last_price) / entry * 100 if direction == "SHORT" else (last_price - entry) / entry * 100
        weighted_pnl += remaining * open_pnl
        if outcome_label == "⏳ هنوز باز":
            if t2_hit:
                outcome_label = "⏳ هدف۱و۲ خورد، بقیه هنوز بازه"
            elif t1_hit:
                outcome_label = "⏳ هدف۱ خورد، بقیه هنوز بازه"

    return outcome_label, last_price, round(weighted_pnl - ESTIMATED_ROUNDTRIP_FEE_PERCENT, 2)


def main():
    all_rows = []

    for coin in COINS:
        symbol = f"{coin}USDT"
        print(f"\n{'='*70}\n{coin} ({symbol})\n{'='*70}")

        try:
            candles = fetch_klines_with_time(symbol, interval="1h", limit=400)
        except Exception as e:
            print(f"❌ نشد کندل‌های {symbol} رو بگیرم: {e}")
            continue

        for hours_ago in HOURS_AGO_LIST:
            scenario_index = len(candles) - hours_ago
            if scenario_index < 100:
                print(f"  رد شد (داده‌ی کافی برای {hours_ago} ساعت پیش نیست)")
                continue

            print(f"\n  سناریو: {hours_ago} ساعت پیش")
            prediction = analyze_at_point(symbol, candles, scenario_index)
            if prediction is None:
                print("   داده‌ی کافی نبود، رد شد")
                continue

            outcome, outcome_price, pnl = check_actual_outcome(candles, scenario_index, prediction)

            pnl_str = f"{pnl:+.2f}٪" if pnl is not None else "—"
            print(f"   زمان: {prediction['time'].strftime('%Y-%m-%d %H:%M UTC')}")
            print(f"   پیش‌بینی: {prediction['direction']}{' (بدون معامله)' if prediction.get('no_trade') else ''} | ورود={prediction['price']} | هدف۱={prediction.get('target_1')} | هدف۲={prediction.get('target_2')} | هدف۳={prediction.get('target_3')} | استاپ={prediction['stop']}")
            print(f"   اطمینان: {prediction['aligned']}/{prediction['total']}")
            print(f"   نتیجه‌ی واقعی: {outcome} (قیمت={outcome_price}) | سود/زیان: {pnl_str}")

            all_rows.append({
                "ارز": coin,
                "زمان_سناریو_UTC": prediction["time"].strftime("%Y-%m-%d %H:%M"),
                "جهت_پیش‌بینی": prediction["direction"],
                "قیمت_ورود": prediction["price"],
                "هدف۱": prediction.get("target_1"),
                "هدف۲_اصلی": prediction.get("target_2") or prediction["target"],
                "هدف۳": prediction.get("target_3"),
                "استاپ": prediction["stop"],
                "استاپ_از_SR": prediction.get("sr_used_for_stop"),
                "اطمینان": f"{prediction['aligned']}/{prediction['total']}",
                "رژیم_بازار": prediction.get("regime"),
                "جهت_روند": prediction.get("trend_direction"),
                "RSI": prediction["rsi"],
                "فاندینگ": prediction["funding_rate"],
                "OI_تغییر": prediction["oi_change"],
                "لانگ_شورت": prediction["ls_ratio"],
                "Fear_Greed": prediction["fg_value"],
                "نتیجه_واقعی": outcome,
                "قیمت_نهایی": outcome_price,
                "سود_زیان_درصد_پله‌ای": pnl,
            })

            time.sleep(0.3)  # جلوگیری از rate limit

    if not all_rows:
        print("\n❌ هیچ سناریویی قابل بررسی نبود.")
        return

    csv_path = "backtest_results.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)

    total = len(all_rows)
    target_hits = sum(1 for r in all_rows if "🎯" in r["نتیجه_واقعی"])
    stop_hits = sum(1 for r in all_rows if "🛑" in r["نتیجه_واقعی"])
    still_open = sum(1 for r in all_rows if "⏳" in r["نتیجه_واقعی"])
    no_trade_count = sum(1 for r in all_rows if "⚪" in r["نتیجه_واقعی"])
    pnl_values = [r["سود_زیان_درصد_پله‌ای"] for r in all_rows if r["سود_زیان_درصد_پله‌ای"] is not None]
    avg_pnl = sum(pnl_values) / len(pnl_values) if pnl_values else 0

    resolved = target_hits + stop_hits
    win_rate = (target_hits / resolved * 100) if resolved else None

    print(f"\n{'='*70}")
    print(f"خلاصه‌ی کلی ({total} سناریو):")
    print(f"  ⚪ بدون معامله (سیگنال ناکافی): {no_trade_count}")
    print(f"  🎯 هدف خورد: {target_hits}")
    print(f"  🛑 استاپ خورد: {stop_hits}")
    print(f"  ⏳ هنوز باز: {still_open}")
    if win_rate is not None:
        print(f"  نرخ موفقیت (از معامله‌های تمام‌شده): {win_rate:.1f}٪")
    print(f"  میانگین سود/زیان (فقط سناریوهایی که واقعاً معامله شدن): {avg_pnl:+.2f}٪")
    print(f"\n✅ فایل کامل: {csv_path}")


if __name__ == "__main__":
    main()
