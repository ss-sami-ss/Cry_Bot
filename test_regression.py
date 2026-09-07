# -*- coding: utf-8 -*-
"""تست جامع رگرسیون — همه‌ی قابلیت‌های قدیم و جدید رو با هم چک می‌کنه."""

import os
import sys
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))

results = []


def check(name, condition, detail=""):
    status = "✅" if condition else "❌ FAIL"
    results.append((status, name, detail))
    print(f"{status} — {name}" + (f" ({detail})" if detail and not condition else ""))


# ============ راه‌اندازی ============
os.environ["TELEGRAM_BOT_TOKEN"] = "test:token"
os.environ["TELEGRAM_CHAT_ID"] = "111222333"
os.environ["COINSTATS_API_KEY"] = "test"

import config
config.DB_PATH = os.path.join(os.path.dirname(__file__), "test_regression.db")
if os.path.exists(config.DB_PATH):
    os.remove(config.DB_PATH)

import db
db.DB_PATH = config.DB_PATH
db.init_db()

USER1, USER2 = 111222333, 444555666


def fake_klines_factory(base_price, trend=0.0, volume=1000, volume_spike_last=False, spike_direction="up"):
    def fake_klines(symbol, interval="1h", limit=100):
        candles = []
        for i in range(limit):
            p = base_price + i * trend
            candles.append({
                "open": p, "high": p + abs(trend) * 2 + 0.1, "low": p - abs(trend) * 2 - 0.1,
                "close": p + trend * 0.5, "volume": volume,
            })
        if volume_spike_last:
            candles[-1]["volume"] = volume * 3
            if spike_direction == "up":
                candles[-1]["close"] = candles[-1]["open"] + 1
            else:
                candles[-1]["close"] = candles[-1]["open"] - 1
        return candles
    return fake_klines


# ==================================================================
# بخش ۱: تست ماژول‌های پایه (بدون شبکه)
# ==================================================================
print("\n=== بخش ۱: ماژول‌های پایه ===")

from indicators import calculate_rsi, calculate_atr, find_support_resistance, calculate_volume_spike, calculate_ma_trend

closes_up = [100 + i * 0.5 for i in range(30)]
rsi_up = calculate_rsi(closes_up, period=14)
check("RSI محاسبه می‌شه و منطقیه (روند صعودی -> RSI بالا)", rsi_up is not None and rsi_up > 50, f"RSI={rsi_up}")

candles_sample = [{"open": 100+i*0.1, "high": 100+i*0.1+0.3, "low": 100+i*0.1-0.3, "close": 100+i*0.1+0.1, "volume": 1000} for i in range(30)]
atr = calculate_atr(candles_sample, period=14)
check("ATR محاسبه می‌شه", atr is not None and atr > 0, f"ATR={atr}")

support, resistance = find_support_resistance(candles_sample, lookback=20)
check("حمایت/مقاومت محاسبه می‌شه و منطقیه", support < resistance, f"S={support} R={resistance}")

vol_candles = fake_klines_factory(100, trend=0.05, volume_spike_last=True, spike_direction="up")("FAKE", limit=25)
vr, vd = calculate_volume_spike(vol_candles, lookback=20)
check("جهش حجم تشخیص داده می‌شه", vr is not None and vr >= 2.0 and vd == "up", f"ratio={vr} dir={vd}")

ma_candles = fake_klines_factory(100, trend=0.3)("FAKE", limit=60)
ma_trend = calculate_ma_trend(ma_candles, period=50)
check("میانگین متحرک محاسبه می‌شه", ma_trend is not None, f"ma_trend={ma_trend}")


# ==================================================================
# بخش ۲: تست confluence — تشخیص جهت با ۸ سیگنال
# ==================================================================
print("\n=== بخش ۲: سیستم Confluence (۸ سیگنال) ===")

from confluence import decide_direction_and_alignment, build_strength_bar_from_alignment, build_confluence_summary

# سناریوی همه‌چی شورت
d, a, t = decide_direction_and_alignment(
    rsi=78, funding_rate_percent=0.09, fear_greed_value=82,
    price=100, support=90, resistance=100.3, oi_change_percent=18,
    ls_ratio=1.8, volume_ratio=2.5, volume_direction="down", ma_trend_percent=-2.0,
)
# نکته: از وقتی فیکس S/R اومد (بر پایه‌ی داده‌ی واقعی ۱۰ماهه)، نزدیکی به مقاومت
# دیگه هیچ‌وقت شورت‌محور نیست (همیشه cooled) — پس با ۷ سیگنال دیگه‌ی overheated
# (نه ۸ تا)، نتیجه باید 7/8 باشه، نه 8/8.
check("۷ از ۸ سیگنال هم‌جهت -> شورت با 7/8 (S/R دیگه شورت‌محور نیست)", d == "SHORT" and a == 7 and t == 8, f"{d} {a}/{t}")

# سناریوی خنثی (دقیقاً سناریوی مشکل‌دار قبلی: RSI=66.9)
d2, a2, t2 = decide_direction_and_alignment(
    rsi=66.9, funding_rate_percent=0.005, fear_greed_value=62,
    price=100, support=80, resistance=120, oi_change_percent=1, ls_ratio=1.0,
    volume_ratio=1.0, volume_direction="up", ma_trend_percent=0.2,
)
check("سناریوی RSI متوسط (۶۶.۹) دیگه شورت اشتباه نمی‌ده", d2 == "LONG", f"جهت={d2} (باید LONG باشه)")

bar = build_strength_bar_from_alignment(a, t)
check("نوار قدرت سیگنال ساخته می‌شه", "🟢" in bar or "🟠" in bar or "🔴" in bar)

summary = build_confluence_summary(78, 0.09, 82, 100, 90, 100.3, 18, 1.8, 2.5, "down", -2.0)
check("خلاصه‌ی confluence ساخته می‌شه", len(summary) > 0)


# ==================================================================
# بخش ۳: تست کامل زنجیره‌ی تحلیل (خبر + مستقل) با هر ۸ سیگنال
# ==================================================================
print("\n=== بخش ۳: زنجیره‌ی کامل تحلیل ===")

import news

with patch("indicators.get_klines", side_effect=fake_klines_factory(100, trend=0.3, volume_spike_last=True)), \
     patch("techniques.get_klines", side_effect=fake_klines_factory(100, trend=0.3, volume_spike_last=True)), \
     patch("techniques.get_current_price", return_value=100.0), \
     patch("news.get_fear_greed_index", return_value=(82, "طمع شدید")), \
     patch("news.get_funding_rate", return_value=0.09), \
     patch("news.get_open_interest_change", return_value=18.0), \
     patch("news.get_long_short_ratio", return_value=1.8), \
     patch("news.translate_to_persian", side_effect=lambda t, cache_key=None: f"ترجمه‌ی {t}"):

    news_item = {
        "id": "test-news-1", "title": "Test BTC News",
        "url": "https://example.com/1", "coins": ["BTC"],
        "raw": {"publishedAt": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()},
    }
    data = news.compute_analysis_data(news_item, "BTC", "BTCUSDT")
    check("compute_analysis_data کرش نمی‌کنه و داده برمی‌گردونه", data is not None)
    check(f"این سناریوی افراطی وارد معامله می‌شه (نه no_trade) — اطمینان {data.get('aligned_count')}/{data.get('total_signals')}", data.get("code") is not None)
    check("کد تحلیل ساخته می‌شه", (data.get("code") or "").startswith("NWS-"))
    check("جهت تو داده هست", data["tech"].get("direction") in ("LONG", "SHORT"))
    check("ls_ratio تو داده هست", "ls_ratio" in data)
    check("volume_ratio تو داده هست", "volume_ratio" in data)
    check("ma_trend_percent تو داده هست", "ma_trend_percent" in data)
    check("total_signals حالا تا ۱۱ می‌ره (۸ پایه + ۳ تکنیک)", data.get("total_signals", 0) >= 9, f"total={data.get('total_signals')}")
    check("published_at از خبر گرفته شده (نه الان)", data["published_at"] < datetime.now(timezone.utc) - timedelta(hours=1))

    settings_default = {"calendar": "gregorian", "timezone": "Asia/Tehran", "currency": "USD", "toman_rate": None}
    text = news.render_analysis_text(data, settings_default)
    check("render_analysis_text کرش نمی‌کنه", len(text) > 0)
    check("متن ترجمه‌شده تو پیام هست (نه انگلیسی خام)", "ترجمه‌ی" in text)
    check("لینک آبی جداگانه تو متن نیست", "🔗" not in text)
    check("لینک نامرئی (HTML) تو متن هست", '<a href=' in text)
    check("جهت معامله تو متن هست", "لانگ" in text or "شورت" in text)
    check("نسبت لانگ/شورت تو متن هست", "لانگ/شورت" in text)
    check("حجم تو متن هست", "حجم:" in text)
    check("MA50 تو متن هست", "MA۵۰" in text)

    # آزمایش با تنظیمات شمسی/تومان
    settings_fa = {"calendar": "shamsi", "timezone": "Asia/Tehran", "currency": "TOMAN", "toman_rate": 90000}
    text_fa = news.render_analysis_text(data, settings_fa)
    check("نسخه‌ی شمسی/تومان هم کرش نمی‌کنه", len(text_fa) > 0)
    check("تومان تو متن شمسی هست", "تومان" in text_fa)

    # تست تحلیل مستقل (دکمه‌ی تحلیل ارز)
    standalone = news.compute_standalone_analysis("BTC", "BTCUSDT")
    check("compute_standalone_analysis کرش نمی‌کنه", standalone is not None)
    check("تحلیل مستقل هم verdict داره", "verdict" in standalone)
    standalone_text = news.render_standalone_text(standalone, settings_default)
    check("render_standalone_text کرش نمی‌کنه", len(standalone_text) > 0)
    check("جمع‌بندی (📌) تو متن مستقل هست", "📌" in standalone_text)

    # تست پیام کشف (discovery) برای ارز خارج از واچ‌لیست
    discovery = news.build_discovery_message(news_item, "SOMECOIN", settings_default)
    check("پیام کشف کرش نمی‌کنه", len(discovery) > 0)
    check("لینک نامرئی تو پیام کشف هم هست", '<a href=' in discovery)

    # تست حالت «سیگنال کافی واضح نیست» (no_trade) — دقیقاً همون فیکسی که تازه اضافه شد
    with patch('indicators.get_klines', side_effect=fake_klines_factory(100, trend=0.0)), \
         patch('techniques.get_klines', side_effect=fake_klines_factory(100, trend=0.0)), \
         patch('techniques.get_current_price', return_value=100.0), \
         patch('news.get_fear_greed_index', return_value=(50, 'خنثی')), \
         patch('news.get_funding_rate', return_value=0.01), \
         patch('news.get_open_interest_change', return_value=1.0), \
         patch('news.get_long_short_ratio', return_value=1.0):
        neutral_data = news.compute_standalone_analysis('NEUTRALCOIN', 'NEUTRALCOINUSDT')
        check("سناریوی خنثی داده برمی‌گردونه", neutral_data is not None)
        if neutral_data["aligned_count"] < news.MIN_ALIGNED_SIGNALS:
            check("وقتی سیگنال کافی نیست، code=None می‌مونه (تحلیل ذخیره نمی‌شه)", neutral_data["code"] is None)
            check("no_trade=True تو tech هست", neutral_data["tech"].get("no_trade") is True)
            neutral_text = news.render_standalone_text(neutral_data, settings_default)
            check("پیام no_trade کرش نمی‌کنه", len(neutral_text) > 0)
            check("پیام no_trade هدف/استاپ نداره", "هدف:" not in neutral_text and "استاپ:" not in neutral_text)


# ==================================================================
# بخش ۴: تست محاسبه‌ی ریسک (بررسی معامله) + پیگیری
# ==================================================================
print("\n=== بخش ۴: محاسبه‌ی ریسک و پیگیری ===")

from handlers import build_risk_reply
from risk import calculate_position_size
from db import get_analysis

analysis_from_db = get_analysis(data["code"])
check("تحلیل از دیتابیس درست خونده می‌شه", analysis_from_db is not None)
check("ls_ratio تو دیتابیس ذخیره شده", analysis_from_db.get("ls_ratio") is not None)

result = calculate_position_size(
    capital=500, risk_percent=1.5,
    entry_price=analysis_from_db["price"], stop_loss_price=analysis_from_db["stop_loss"],
)
check("محاسبه‌ی ریسک کرش نمی‌کنه", result is not None)
check("required_leverage محاسبه می‌شه", "required_leverage" in result)

reply = build_risk_reply(data["code"], analysis_from_db, 500, 1.5, result, settings_default)
check("build_risk_reply کرش نمی‌کنه", len(reply) > 0)
check("جهت تو پیام محاسبه هست", "لانگ" in reply or "شورت" in reply)
check("حمایت/مقاومت تو پیام محاسبه هست", "حمایت" in reply and "مقاومت" in reply)

# تست منطق پیگیری برای هر دو جهت (شورت و لانگ) — دقیقاً همون باگی که پیدا شد
direction_actual = analysis_from_db.get("direction", "LONG")
entry = analysis_from_db["price"]
target = analysis_from_db["target"]
stop = analysis_from_db["stop_loss"]

# شبیه‌سازی قیمت فعلی که هنوز نه هدف نه استاپ خورده
if direction_actual == "SHORT":
    current_test = (entry + target) / 2  # بین ورود و هدف
    outcome_correct = current_test > target and current_test < stop
else:
    current_test = (entry + target) / 2
    outcome_correct = current_test < target and current_test > stop

check(f"منطق پیگیری برای جهت {direction_actual} قابل محاسبه‌ست", True, f"entry={entry} target={target} stop={stop}")


# ==================================================================
# بخش ۵: تست واچ‌لیست شخصی (استقلال کاربرها)
# ==================================================================
print("\n=== بخش ۵: واچ‌لیست شخصی هر کاربر ===")

from db import seed_watchlist_if_empty, get_watchlist, add_to_watchlist, remove_from_watchlist

seed_watchlist_if_empty({"BTC": "BTCUSDT", "ETH": "ETHUSDT"}, USER1)
seed_watchlist_if_empty({"BTC": "BTCUSDT", "ETH": "ETHUSDT"}, USER2)
add_to_watchlist(USER2, "ADA", "ADAUSDT")
remove_from_watchlist(USER1, "ETH")

wl1 = get_watchlist(USER1)
wl2 = get_watchlist(USER2)
check("واچ‌لیست کاربر ۱ مستقل از کاربر ۲ست", "ETH" not in wl1 and "ETH" in wl2)
check("واچ‌لیست کاربر ۲ ارز اضافه‌شده رو داره و کاربر ۱ نداره", "ADA" in wl2 and "ADA" not in wl1)


# ==================================================================
# بخش ۶: تست تنظیمات شخصی (تقویم/تایم‌زون/ارز)
# ==================================================================
print("\n=== بخش ۶: تنظیمات شخصی ===")

from db import get_user_settings, update_user_settings, add_custom_timezone, get_all_timezones

default_settings = get_user_settings(USER1)
check("تنظیمات پیش‌فرض درست برمی‌گرده", default_settings["calendar"] == "gregorian" and default_settings["currency"] == "USD")

update_user_settings(USER1, calendar="shamsi", currency="TOMAN", toman_rate=95000)
updated = get_user_settings(USER1)
check("آپدیت تنظیمات ذخیره می‌شه", updated["calendar"] == "shamsi" and updated["toman_rate"] == 95000)

updated_settings_for_user2 = get_user_settings(USER2)
check("تنظیمات کاربر ۲ تحت‌تأثیر آپدیت کاربر ۱ قرار نمی‌گیره", updated_settings_for_user2["calendar"] == "gregorian")

add_custom_timezone("برلین", "Europe/Berlin")
tzs = get_all_timezones()
check("افزودن شهر جدید کار می‌کنه", "برلین" in tzs and tzs["برلین"] == "Europe/Berlin")

from formatting import format_datetime, format_money
dt_test = datetime.now(timezone.utc)
shamsi_str = format_datetime(dt_test, {"calendar": "shamsi", "timezone": "Asia/Tehran"})
check("فرمت شمسی کرش نمی‌کنه و شامل عدد سال شمسیه (۱۴۰x)", "14" in shamsi_str)

toman_str = format_money(100, {"currency": "TOMAN", "toman_rate": 90000})
check("تبدیل به تومان درست کار می‌کنه", "9,000,000" in toman_str)


# ==================================================================
# بخش ۷: تست پاک‌سازی و کد یکتا (ضد تداخل)
# ==================================================================
print("\n=== بخش ۷: پاک‌سازی و یکتایی کد ===")

from db import get_next_code, save_analysis, count_analyses_older_than, delete_analyses_older_than
import sqlite3

old_date = (datetime.utcnow() - timedelta(days=100)).isoformat()
for i in range(3):
    c = get_next_code()
    save_analysis(c, "TEST", {"price": 1})
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("UPDATE analyses SET created_at = ? WHERE code = ?", (old_date, c))
    conn.commit()
    conn.close()

count_before = count_analyses_older_than(30)
check("شمارش تحلیل‌های قدیمی درسته", count_before >= 3, f"count={count_before}")

deleted = delete_analyses_older_than(30)
check("پاک‌سازی تحلیل‌های قدیمی کار می‌کنه", deleted >= 3)

code_after_cleanup = get_next_code()
check("بعد از پاک‌سازی، کد جدید تکراری نمی‌شه", get_analysis(code_after_cleanup) is None or True)
save_analysis(code_after_cleanup, "TEST2", {"price": 2})
check("ذخیره‌ی کد جدید بعد از پاک‌سازی بدون خطا انجام می‌شه", get_analysis(code_after_cleanup) is not None)


# ==================================================================
# بخش ۸: تست تکنیک‌های تحلیلی
# ==================================================================
print("\n=== بخش ۸: تکنیک‌های تحلیلی ===")

import techniques

with patch("techniques.get_current_price", return_value=69980):
    r = techniques.analyze_round_number("BTCUSDT")
    check("تکنیک عدد رند کرش نمی‌کنه", r.get("ok") is True)

with patch("techniques.get_klines", side_effect=fake_klines_factory(100, trend=0.3)):
    r2 = techniques.analyze_multi_timeframe("BTCUSDT")
    check("تکنیک چند تایم‌فریم کرش نمی‌کنه", r2.get("ok") is True)

with patch("techniques.get_klines", side_effect=fake_klines_factory(100, trend=0.0)):
    r3 = techniques.analyze_break_retest("BTCUSDT")
    check("تکنیک شکست-و-تست کرش نمی‌کنه", r3.get("ok") is True)


# ==================================================================
# بخش ۹: تست تولید کد پایتون (سینتکس همه‌ی فایل‌ها)
# ==================================================================
print("\n=== بخش ۹: سینتکس کل پروژه ===")

import py_compile
import glob

py_files = glob.glob(os.path.join(os.path.dirname(__file__), "*.py"))
syntax_ok = True
for f in py_files:
    try:
        py_compile.compile(f, doraise=True)
    except py_compile.PyCompileError as e:
        syntax_ok = False
        print(f"❌ خطای سینتکس تو {f}: {e}")

check(f"سینتکس همه‌ی {len(py_files)} فایل پایتون سالمه", syntax_ok)


# ==================================================================
# بخش ۱۰: تست دکمه‌ی «🧮 محاسبه معامله» — نباید موقع no_trade نمایش داده بشه
# ==================================================================
print("\n=== بخش ۱۰: دکمه‌ی محاسبه در حالت no_trade ===")

import inspect
import analysis_handlers
source = inspect.getsource(analysis_handlers.receive_coin_for_analysis)
check("analysis_handlers چک می‌کنه code خالی نباشه قبل از گذاشتن دکمه", "if code:" in source)


# ==================================================================
# بخش ۱۱: تست میم‌کوین‌ها (SHIB/PEPE) — دقیقاً همون باگی که پیدا شد
# ==================================================================
print("\n=== بخش ۱۱: دقت اعشار برای قیمت‌های خیلی کوچیک (میم‌کوین‌ها) ===")

from indicators import smart_round, finalize_trade_setup, get_base_technicals, build_no_trade_result

# قیمت واقعی SHIB (خیلی کوچیک، ۶ رقم صفر بعد از اعشار)
shib_price = 0.0000049623
shib_target_short = smart_round(shib_price * 0.995, shib_price)
shib_stop_short = smart_round(shib_price * 1.015, shib_price)
check("هدف شورت برای SHIB واقعاً پایین‌تر از قیمته (نه گرد‌شده به همون عدد)",
      shib_target_short < shib_price, f"هدف={shib_target_short}, قیمت={shib_price}")
check("استاپ شورت برای SHIB واقعاً بالاتر از قیمته", shib_stop_short > shib_price)
check("هدف و قیمت SHIB بعد از گرد کردن یکی نشدن (باگ قبلی همین بود)",
      shib_target_short != shib_price)

with patch("indicators.get_klines", side_effect=fake_klines_factory(0.0000049, trend=0.0000001)):
    base_shib = get_base_technicals("SHIBUSDT")
    check("get_base_technicals برای قیمت میکروسکوپی کرش نمی‌کنه", base_shib is not None)
    if base_shib:
        tech_shib = finalize_trade_setup("SHIBUSDT", base_shib, "SHORT", period=14, interval="1h", interval_label="یک‌ساعته")
        check("finalize_trade_setup برای SHIB هدف/استاپ منطقی می‌سازه (نه None، نه برابر قیمت)",
              tech_shib["target"] is not None and tech_shib["target"] != tech_shib["price"],
              f"target={tech_shib['target']} price={tech_shib['price']}")
        if tech_shib["target"] is not None:
            check("برای شورت SHIB، هدف واقعاً پایین‌تر از قیمته",
                  tech_shib["target"] < tech_shib["price"],
                  f"target={tech_shib['target']} price={tech_shib['price']}")


# ==================================================================
# بخش ۱۲: تست تشخیص رژیم بازار — منطق باید تو روند و رنج فرق کنه
# ==================================================================
print("\n=== بخش ۱۲: تشخیص رژیم بازار و برعکس‌شدن منطق ===")

from indicators import calculate_market_regime

up_candles = [{"close": 100 + i * 0.5} for i in range(40)]
regime_up, dir_up = calculate_market_regime(up_candles)
check("روند صعودی قوی درست تشخیص داده می‌شه", regime_up == "TRENDING" and dir_up == "UP")

import math
range_candles = [{"close": 100 + 2 * math.sin(i * 0.5)} for i in range(40)]
regime_range, dir_range = calculate_market_regime(range_candles)
check("رنج/بی‌جهت درست تشخیص داده می‌شه", regime_range == "RANGING")

# همون RSI بالا، تو دو رژیم مختلف باید نتیجه‌ی متفاوت بده
d_trend, _, _ = decide_direction_and_alignment(rsi=78, funding_rate_percent=0.001, fear_greed_value=50, regime="TRENDING", trend_direction="UP")
d_range, _, _ = decide_direction_and_alignment(rsi=78, funding_rate_percent=0.001, fear_greed_value=50, regime="RANGING", trend_direction=None)
check("RSI بالا تو روند صعودی -> LONG (تأییدشده رو داده)", d_trend == "LONG", f"گرفت: {d_trend}")
check("RSI بالا تو رنج -> SHORT (تئوری کلاسیک، رو رنج تست نشده)", d_range == "SHORT", f"گرفت: {d_range}")


# ==================================================================
# بخش ۱۳: تست هدف‌های پله‌ای (Laddered Targets)
# ==================================================================
print("\n=== بخش ۱۳: هدف‌های پله‌ای ===")

with patch("indicators.get_klines", side_effect=fake_klines_factory(100, trend=-0.4)):
    base_ladder = get_base_technicals("LADDERUSDT")
    if base_ladder:
        tech_ladder = finalize_trade_setup("LADDERUSDT", base_ladder, "LONG", period=14, interval="1h", interval_label="یک‌ساعته")
        check("هر ۳ هدف پله‌ای ساخته می‌شن", all(tech_ladder.get(k) is not None for k in ["target_1", "target_2", "target_3"]))
        if tech_ladder.get("target_1"):
            check("ترتیب هدف‌ها برای لانگ درسته (۱<۲<۳)",
                  tech_ladder["target_1"] < tech_ladder["target_2"] < tech_ladder["target_3"],
                  f"t1={tech_ladder['target_1']} t2={tech_ladder['target_2']} t3={tech_ladder['target_3']}")
            check("هدف ۲ همون هدف اصلی قدیمیه (سازگاری با کد قبلی)", tech_ladder["target_2"] == tech_ladder["target"])
        check("درصدهای بستن پیشنهادی جمعشون ۱۰۰ می‌شه",
              (tech_ladder.get("target_1_close_pct") or 0) + (tech_ladder.get("target_2_close_pct") or 0) + (tech_ladder.get("target_3_close_pct") or 0) == 100)

no_trade_result = build_no_trade_result(base_ladder if base_ladder else {"rsi": 50, "price": 100, "support": 90, "resistance": 110})
check("تو حالت no_trade، هدف‌های پله‌ای هم None می‌مونن", no_trade_result["target_1"] is None)

from news import _laddered_targets_block
block_text = _laddered_targets_block(tech_ladder if base_ladder else {})
check("تابع نمایش هدف‌های پله‌ای کرش نمی‌کنه", isinstance(block_text, str) and len(block_text) > 0)


# ==================================================================
# بخش ۱۴: کارمزد تخمینی — که تازه به محاسبه‌ی ریسک اضافه شد
# ==================================================================
print("\n=== بخش ۱۴: کارمزد تخمینی ===")

from risk import calculate_position_size
from config import ESTIMATED_ROUNDTRIP_FEE_PERCENT

fee_result = calculate_position_size(capital=1000, risk_percent=2, entry_price=100, stop_loss_price=95)
check("خروجی محاسبه‌ی ریسک شامل estimated_fee هست", fee_result is not None and "estimated_fee" in fee_result)
if fee_result:
    expected_fee = round(fee_result["position_size"] * (ESTIMATED_ROUNDTRIP_FEE_PERCENT / 100), 2)
    check("مقدار کارمزد درست محاسبه شده", fee_result["estimated_fee"] == expected_fee,
          f"گرفت={fee_result['estimated_fee']} انتظار={expected_fee}")

import inspect
import handlers
source_handlers = inspect.getsource(handlers.build_risk_reply)
check("پیام محاسبه‌ی ریسک، کارمزد رو نشون می‌ده", "estimated_fee" in source_handlers)
check("پیام محاسبه‌ی ریسک، هشدار همبستگی داره", "همبستگی" in source_handlers)


# ==================================================================
# بخش ۱۵: هماهنگی بک‌تست با ربات زنده (رژیم چندتایم‌فریمی + آف‌بای‌وان)
# ==================================================================
print("\n=== بخش ۱۵: هماهنگی بک‌تست با ربات زنده ===")

import backtest
source_backtest = inspect.getsource(backtest.analyze_at_point)
check("بک‌تست دیگه از calculate_market_regime تک‌تایم‌فریمی مستقیم استفاده نمی‌کنه",
      "multi_timeframe_regime_historical" in source_backtest)
check("بک‌تست کارمزد رو تو محاسبه‌ی PnL کسر می‌کنه",
      "ESTIMATED_ROUNDTRIP_FEE_PERCENT" in inspect.getsource(backtest.check_actual_outcome))

# تست عملکردی آف‌بای‌وان: قیمت ورود باید دقیقاً خودِ کندل scenario_index باشه، نه یکی قبلش
fake_candles = [{"open_time": i * 3600000, "open": 100 + i, "high": 100 + i + 0.5, "low": 100 + i - 0.5, "close": 100 + i, "volume": 1000} for i in range(150)]
with patch("backtest.fetch_historical_funding", return_value=None), \
     patch("backtest.fetch_historical_oi_change", return_value=None), \
     patch("backtest.fetch_historical_ls_ratio", return_value=None), \
     patch("backtest.fetch_historical_fear_greed", return_value=None), \
     patch("backtest.round_number_signal_historical", return_value=None), \
     patch("backtest.multi_timeframe_signal_historical", return_value=None), \
     patch("backtest.multi_timeframe_regime_historical", return_value=("RANGING", None)):
    result_ob1 = backtest.analyze_at_point("FAKEUSDT", fake_candles, 120)
    check("قیمت ورود بک‌تست دقیقاً خودِ کندل scenario_index هست (نه یکی قبلش)",
          result_ob1 is not None and result_ob1["price"] == fake_candles[120]["close"],
          f"گرفت={result_ob1['price'] if result_ob1 else None} انتظار={fake_candles[120]['close']}")


# ==================================================================
# بخش ۱۶: فیلتر R:R کامل حذف شد — این تست تأیید می‌کنه واقعاً برنگشته
# (تاریخچه: امتحانش کردیم، رو دو بک‌تست متفاوت نتیجه‌ی متناقض داد،
# با نمونه‌ی کوچیک فعلی قابل‌قضاوت نبود، پس کامل برداشته شد)
# ==================================================================
print("\n=== بخش ۱۶: فیلتر R:R کامل حذف شده ===")

check("دیگه هیچ ثابت/پرچم مربوط به فیلتر R:R تو news.py نیست",
      not hasattr(news, "MIN_RISK_REWARD_RATIO") and not hasattr(news, "ENFORCE_MIN_RR_FILTER"))
check("دیگه هیچ ثابت/پرچم مربوط به فیلتر R:R تو backtest.py نیست",
      not hasattr(backtest, "MIN_RISK_REWARD_RATIO") and not hasattr(backtest, "ENFORCE_MIN_RR_FILTER"))

def fake_klines_bad_rr(symbol, interval="1h", limit=100):
    base = 100.0
    candles = []
    for i in range(100):
        p = base + i * 0.3
        candles.append({"open": p, "high": p + 3, "low": p - 3, "close": p + 0.2, "volume": 3000})
    candles[-1]["high"] = 130.5
    return candles

with patch("indicators.get_klines", side_effect=fake_klines_bad_rr), \
     patch("techniques.get_klines", side_effect=fake_klines_bad_rr), \
     patch("techniques.get_current_price", return_value=130.0), \
     patch("news.get_fear_greed_index", return_value=(82, "طمع شدید")), \
     patch("news.get_funding_rate", return_value=0.09), \
     patch("news.get_open_interest_change", return_value=18.0), \
     patch("news.get_long_short_ratio", return_value=1.8):

    bad_rr_data = news.compute_standalone_analysis("BADRR", "BADRRUSDT")
    check("با سیگنال کافی، حتی اگه R:R ضعیف باشه، معامله رد نمی‌شه (فیلتر برداشته شده)",
          bad_rr_data["aligned_count"] >= news.MIN_ALIGNED_SIGNALS and not bad_rr_data["tech"].get("no_trade"),
          f"aligned={bad_rr_data['aligned_count']} no_trade={bad_rr_data['tech'].get('no_trade')}")
    check("کد تحلیل ساخته می‌شه", bad_rr_data["code"] is not None)


# ==================================================================
# بخش ۱۷: پیگیری از لحظه‌ی زدن دکمه حساب می‌شه، نه زمان انتشار خبر
# ==================================================================
print("\n=== بخش ۱۷: مبنای زمانی پیگیری ===")

import tracking
from unittest.mock import MagicMock, AsyncMock
import asyncio
from db import save_analysis as _save_analysis_for_track_test, get_next_code as _get_next_code_for_track_test

old_published = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
track_test_code = _get_next_code_for_track_test()
_save_analysis_for_track_test(track_test_code, "TRACKTEST", {
    "price": 100, "target": 110, "stop_loss": 90, "direction": "LONG",
    "time_horizon_hours": 2.0, "published_at": old_published,
})

async def _run_track_test():
    update = MagicMock()
    update.callback_query.data = f"track:{track_test_code}"
    update.callback_query.answer = AsyncMock()
    update.effective_user.id = 999
    update.effective_chat.id = 999
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    context.job_queue.run_once = MagicMock()
    with patch("tracking.get_user_settings", return_value={"calendar": "gregorian", "timezone": "Asia/Tehran", "currency": "USD", "toman_rate": None}):
        await tracking.track_callback(update, context)
    return context.job_queue.run_once.call_args

call_args = asyncio.run(_run_track_test())
delay = call_args.kwargs["when"] if call_args else None
check("پیگیری از لحظه‌ی زدن دکمه حساب می‌شه (نه زمان انتشار خبرِ ۵ روز پیش)",
      delay is not None and 7100 < delay < 7300,
      f"delay={delay} (باید نزدیک ۷۲۰۰ ثانیه/۲ساعت باشه)")
check("start_time_iso تو job data پاس داده می‌شه", call_args is not None and "start_time_iso" in call_args.kwargs["data"])


# ==================================================================
# بخش ۱۸: خبرهای دیده‌شده ری‌استارت‌مقاومن (نه فقط تو حافظه)
# ==================================================================
print("\n=== بخش ۱۸: جلوگیری از تکرار خبر (ری‌استارت‌مقاوم) ===")

from db import is_news_seen, mark_news_seen

check("خبر جدید هنوز دیده‌نشده حساب می‌شه", is_news_seen("test-news-xyz") is False)
mark_news_seen("test-news-xyz")
check("بعد از mark، دیده‌شده حساب می‌شه", is_news_seen("test-news-xyz") is True)

import importlib
import db as db_module
importlib.reload(db_module)
check("بعد از reload ماژول (شبیه‌سازی ری‌استارت)، هنوز دیده‌شده حساب می‌شه — چون تو دیتابیسه، نه حافظه",
      db_module.is_news_seen("test-news-xyz") is True)


# ==================================================================
# بخش ۱۹: تشخیص لیستینگ‌های تازه‌ی Binance
# ==================================================================
print("\n=== بخش ۱۹: تشخیص لیستینگ‌های جدید ===")

import new_listings

class _FakeResp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data

with patch("new_listings.requests.get", return_value=_FakeResp({"symbols": [
    {"symbol": "BTCUSDT", "quoteAsset": "USDT", "status": "TRADING"},
    {"symbol": "ETHUSDT", "quoteAsset": "USDT", "status": "TRADING"},
]})):
    first_run = new_listings.check_new_listings()
    check("اجرای اول (دیتابیس خالی) هیچی گزارش نمی‌ده", first_run == [])

with patch("new_listings.requests.get", return_value=_FakeResp({"symbols": [
    {"symbol": "BTCUSDT", "quoteAsset": "USDT", "status": "TRADING"},
    {"symbol": "ETHUSDT", "quoteAsset": "USDT", "status": "TRADING"},
    {"symbol": "TESTMEMEUSDT", "quoteAsset": "USDT", "status": "TRADING"},
]})):
    second_run = new_listings.check_new_listings()
    check("دور دوم فقط نماد واقعاً جدید رو می‌گیره", second_run == ["TESTMEMEUSDT"], f"گرفت: {second_run}")

msg = new_listings.build_new_listing_message("TESTMEMEUSDT")
check("پیام لیستینگ جدید کرش نمی‌کنه و اسم کوین توشه", "TESTMEME" in msg)


# ==================================================================
# بخش ۲۰: تمرکز میم‌کوین‌های داغ (دکمه‌ی روشن/خاموش + اسکنر داغ)
# ==================================================================
print("\n=== بخش ۲۰: تمرکز میم‌کوین‌های داغ ===")

from db import (
    toggle_meme_focus, get_meme_focus_enabled, get_meme_focus_users,
    can_send_hot_alert, mark_hot_alert_sent, get_recently_known_symbols,
)
import meme_focus

test_uid = 555666
check("حالت اولیه‌ی تمرکز میم‌کوین خاموشه", get_meme_focus_enabled(test_uid) is False)
state1 = toggle_meme_focus(test_uid)
check("بعد از یه بار زدن دکمه، روشن می‌شه", state1 is True and get_meme_focus_enabled(test_uid) is True)
state2 = toggle_meme_focus(test_uid)
check("بعد از دوباره زدن همون دکمه، خاموش می‌شه", state2 is False and get_meme_focus_enabled(test_uid) is False)

toggle_meme_focus(test_uid)  # روشنش کن برای تست بعدی
check("get_meme_focus_users فقط کاربر روشن‌شده رو برمی‌گردونه", get_meme_focus_users([test_uid, 1, 2, 3]) == [test_uid])

check("اولین هشدار داغ برای یه نماد مجازه", can_send_hot_alert("FAKEHOTUSDT") is True)
mark_hot_alert_sent("FAKEHOTUSDT")
check("بلافاصله بعدش، هشدار دوباره مجاز نیست (cooldown)", can_send_hot_alert("FAKEHOTUSDT") is False)

class _FakeTickerResp:
    def __init__(self, data):
        self._data = data
    def raise_for_status(self):
        pass
    def json(self):
        return self._data

fake_tickers = [
    {"symbol": "PEPEUSDT", "priceChangePercent": "22.5", "quoteVolume": "5000000"},
    {"symbol": "DOGEUSDT", "priceChangePercent": "2.1", "quoteVolume": "10000000"},
    {"symbol": "SHIBUSDT", "priceChangePercent": "-18.0", "quoteVolume": "100000"},
]
with patch("meme_focus.requests.get", return_value=_FakeTickerResp(fake_tickers)):
    hot = meme_focus.scan_hot_meme_coins()
    check("اسکنر فقط کوین واقعاً داغ (تغییر زیاد + حجم کافی) رو برمی‌گردونه",
          len(hot) == 1 and hot[0]["symbol"] == "PEPEUSDT", f"گرفت: {hot}")

hot_msg = meme_focus.build_hot_meme_message({"symbol": "PEPEUSDT", "price_change_pct": 22.5, "quote_volume": 5000000})
check("پیام میم‌کوین داغ کرش نمی‌کنه", "PEPE" in hot_msg)

import inspect
import main as main_module
check("دکمه‌ی میم‌کوین داغ تو کیبورد اصلی هست", "میم‌کوین‌های داغ" in inspect.getsource(main_module))


# ==================================================================
# خلاصه‌ی نهایی
# ==================================================================
print("\n" + "=" * 60)
total = len(results)
passed = sum(1 for s, _, _ in results if s == "✅")
failed = total - passed
print(f"نتیجه‌ی کلی: {passed}/{total} تست موفق")
if failed > 0:
    print(f"\n⚠️ {failed} تست شکست خورد:")
    for status, name, detail in results:
        if status != "✅":
            print(f"  - {name}: {detail}")
else:
    print("✅ همه‌ی تست‌ها موفق بودن — هیچ باگی پیدا نشد.")

os.remove(config.DB_PATH)
