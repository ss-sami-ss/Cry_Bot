# -*- coding: utf-8 -*-
"""
فاز ۰ (نسخه‌ی گسترش‌یافته): جمع‌آوری داده‌ی خام از یه بازه‌ی طولانی‌تر (۹ ماه).

نسخه‌ی قبلی فقط ۳۰ روز رو پوشش می‌داد که همه‌ش تصادفاً یه رژیم (صعودی) بود.
این نسخه بازه رو به ۹ ماه گسترش می‌ده (با کندل ۴ساعته به‌جای ۱ساعته، که حجم
داده مدیریت‌پذیر بمونه) تا احتمالاً چندتا رژیم مختلف (صعودی/نزولی/رنج) رو
تو داده ببینیم — و بشه فرضیه‌ی «سیگنال‌ها تو روند برعکس عمل می‌کنن» رو
رو دوره‌های متنوع‌تر تست کرد، نه فقط یه ماه خاص.

⚠️ محدودیت واقعی: فاندینگ/OI/نسبت‌لانگ‌شورت رو Binance فقط ~۳۰ روز اخیر نگه
می‌داره — برای داده‌ی قدیمی‌تر این ستون‌ها خالی می‌مونن (طبیعیه، نه باگ).
سیگنال‌های قیمت‌محور (RSI، MA، رژیم بازار) براي کل بازه کامل موجودن.

اجرا:
    python3 data_research.py

خروجی: research_data.csv
"""

import csv
import time
from datetime import datetime, timezone

import requests

from indicators import (
    calculate_rsi, calculate_atr, find_support_resistance,
    calculate_volume_spike, calculate_ma_trend, calculate_market_regime,
)

COINS = ["BTC", "ETH", "XRP", "SOL", "DOGE", "SHIB", "PEPE", "ADA", "BNB"]
WINDOW_DAYS = 270  # حدود ۹ ماه — برای پوشش چندتا رژیم مختلف بازار
RESEARCH_INTERVAL = "4h"  # کندل درشت‌تر که حجم داده برای ۹ ماه مدیریت‌پذیر بمونه
INTERVAL_HOURS = 4
FORWARD_HOURS = [4, 8, 24]  # چند ساعت بعد رو به‌عنوان "نتیجه" ثبت کنیم

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
BINANCE_FUNDING_HIST_URL = "https://fapi.binance.com/fapi/v1/fundingRate"
BINANCE_OI_HIST_URL = "https://fapi.binance.com/futures/data/openInterestHist"
BINANCE_LS_RATIO_URL = "https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
FEAR_GREED_URL = "https://api.alternative.me/fng/"


def fetch_full_klines(symbol, interval=RESEARCH_INTERVAL, days=WINDOW_DAYS):
    """کندل‌های کامل رو با صفحه‌بندی می‌گیره (Binance هر درخواست حداکثر ۱۰۰۰ تا می‌ده)."""
    all_candles = []
    end_time = None
    candles_per_day = 24 // INTERVAL_HOURS
    needed = days * candles_per_day + 150  # کمی بیشتر برای بافر محاسبات

    while len(all_candles) < needed:
        params = {"symbol": symbol, "interval": interval, "limit": 1000}
        if end_time:
            params["endTime"] = end_time
        resp = requests.get(BINANCE_KLINES_URL, params=params, timeout=15)
        resp.raise_for_status()
        raw = resp.json()
        if not raw:
            break
        candles = [
            {"open_time": int(k[0]), "open": float(k[1]), "high": float(k[2]),
             "low": float(k[3]), "close": float(k[4]), "volume": float(k[5])}
            for k in raw
        ]
        all_candles = candles + all_candles
        end_time = candles[0]["open_time"] - 1
        if len(raw) < 1000:
            break
        time.sleep(0.2)

    return all_candles


def fetch_funding_series(symbol, days=30):
    """کل تاریخچه‌ی فاندینگ رو یه‌جا می‌گیره (نه هر نقطه جدا)."""
    try:
        resp = requests.get(
            BINANCE_FUNDING_HIST_URL,
            params={"symbol": symbol, "limit": 1000},
            timeout=15,
        )
        resp.raise_for_status()
        return [(int(d["fundingTime"]), float(d["fundingRate"]) * 100) for d in resp.json()]
    except Exception as e:
        print(f"  [هشدار] تاریخچه‌ی فاندینگ نگرفت: {e}")
        return []


def fetch_oi_series(symbol, days=30):
    try:
        resp = requests.get(
            BINANCE_OI_HIST_URL,
            params={"symbol": symbol, "period": "1h", "limit": min(days * 24, 500)},
            timeout=15,
        )
        resp.raise_for_status()
        return [(int(d["timestamp"]), float(d["sumOpenInterest"])) for d in resp.json()]
    except Exception as e:
        print(f"  [هشدار] تاریخچه‌ی OI نگرفت: {e}")
        return []


def fetch_ls_ratio_series(symbol, days=30):
    try:
        resp = requests.get(
            BINANCE_LS_RATIO_URL,
            params={"symbol": symbol, "period": "1h", "limit": min(days * 24, 500)},
            timeout=15,
        )
        resp.raise_for_status()
        return [(int(d["timestamp"]), float(d["longShortRatio"])) for d in resp.json()]
    except Exception as e:
        print(f"  [هشدار] تاریخچه‌ی لانگ/شورت نگرفت: {e}")
        return []


def fetch_fear_greed_series(days=30):
    try:
        resp = requests.get(FEAR_GREED_URL, params={"limit": days + 5}, timeout=15)
        resp.raise_for_status()
        return [(int(d["timestamp"]) * 1000, int(d["value"])) for d in resp.json().get("data", [])]
    except Exception as e:
        print(f"  [هشدار] تاریخچه‌ی Fear&Greed نگرفت: {e}")
        return []


def nearest_value(series, target_ms, max_gap_ms=None):
    """نزدیک‌ترین مقدار به یه زمان مشخص رو از یه سری تاریخی پیدا می‌کنه."""
    if not series:
        return None
    best_ts, best_val = min(series, key=lambda p: abs(p[0] - target_ms))
    if max_gap_ms and abs(best_ts - target_ms) > max_gap_ms:
        return None
    return best_val


def series_change_percent(series, target_ms, hours_back=24):
    """درصد تغییر یه سری (مثلاً OI) در N ساعت منتهی به یه زمان مشخص."""
    if not series:
        return None
    window = [v for ts, v in series if target_ms - hours_back * 3600 * 1000 <= ts <= target_ms]
    if len(window) < 2 or window[0] == 0:
        return None
    return round((window[-1] - window[0]) / window[0] * 100, 2)


def main():
    rows = []

    for coin in COINS:
        symbol = f"{coin}USDT"
        print(f"\n{'='*60}\n{coin} — در حال دانلود داده‌ی تا {WINDOW_DAYS} روز اخیر (کندل {RESEARCH_INTERVAL})...")

        try:
            candles = fetch_full_klines(symbol, RESEARCH_INTERVAL, WINDOW_DAYS)
        except Exception as e:
            print(f"❌ کندل‌ها نیومد: {e}")
            continue

        if len(candles) < 150:
            print(f"داده‌ی کافی نیست (فقط {len(candles)} کندل — احتمالاً ارز خیلی جدیده)، رد شد")
            continue

        actual_days = (candles[-1]["open_time"] - candles[0]["open_time"]) / (1000 * 3600 * 24)
        print(f"واقعاً {actual_days:.0f} روز داده در دسترس بود")

        funding_series = fetch_funding_series(symbol)
        oi_series = fetch_oi_series(symbol)
        ls_series = fetch_ls_ratio_series(symbol)
        fg_series = fetch_fear_greed_series(days=WINDOW_DAYS)

        # افق‌های زمانی رو از ساعت به تعداد کندل (بر اساس تایم‌فریم تحقیق) تبدیل می‌کنیم
        forward_steps = [max(1, h // INTERVAL_HOURS) for h in FORWARD_HOURS]
        max_future_step = max(forward_steps)

        start_idx = 100
        end_idx = len(candles) - max_future_step - 1

        print(f"در حال محاسبه‌ی سیگنال‌ها برای {max(0, end_idx - start_idx)} نقطه‌ی زمانی...")

        for i in range(start_idx, end_idx):
            window = candles[i - 100:i]
            closes = [c["close"] for c in window]
            price = closes[-1]
            at_time_ms = candles[i]["open_time"]

            rsi = calculate_rsi(closes, period=14)
            atr = calculate_atr(window, period=14)
            support, resistance = find_support_resistance(window, lookback=50)
            volume_ratio, volume_direction = calculate_volume_spike(window, lookback=20)
            ma_trend_percent = calculate_ma_trend(window, period=50)
            regime, trend_direction = calculate_market_regime(window, lookback=30)

            funding_rate = nearest_value(funding_series, at_time_ms, max_gap_ms=9 * 3600 * 1000)
            oi_change = series_change_percent(oi_series, at_time_ms, hours_back=24)
            ls_ratio = nearest_value(ls_series, at_time_ms, max_gap_ms=2 * 3600 * 1000)
            fg_value = nearest_value(fg_series, at_time_ms, max_gap_ms=36 * 3600 * 1000)

            row = {
                "coin": coin,
                "time": datetime.fromtimestamp(at_time_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
                "price": price,
                "rsi": rsi,
                "atr_percent": round(atr / price * 100, 3) if atr else None,
                "funding_rate": funding_rate,
                "oi_change_24h": oi_change,
                "ls_ratio": ls_ratio,
                "fear_greed": fg_value,
                "volume_ratio": volume_ratio,
                "volume_direction": volume_direction,
                "ma_trend_percent": ma_trend_percent,
                "regime": regime,
                "trend_direction": trend_direction,
                "dist_to_support_pct": round((price - support) / price * 100, 3) if support else None,
                "dist_to_resistance_pct": round((resistance - price) / price * 100, 3) if resistance else None,
            }

            # برچسب‌ها: قیمت واقعاً N ساعت بعد چقدر تغییر کرد (بر پایه‌ی تعداد کندل، نه ساعت خام)
            for h, step in zip(FORWARD_HOURS, forward_steps):
                future_price = candles[i + step]["close"]
                row[f"forward_return_{h}h_pct"] = round((future_price - price) / price * 100, 3)

            rows.append(row)

        time.sleep(0.5)

    if not rows:
        print("\n❌ هیچ داده‌ای جمع نشد.")
        return

    csv_path = "research_data.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n{'='*60}")
    print(f"✅ {len(rows)} ردیف داده جمع شد — فایل: {csv_path}")
    print("این فایل رو بفرست تا فاز ۱ (تحلیل آماری) رو روش انجام بدم.")


if __name__ == "__main__":
    main()
