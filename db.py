# -*- coding: utf-8 -*-
"""
مدیریت ذخیره‌سازی تحلیل‌ها.
هر تحلیلی که ربات می‌فرسته، با یه کد یکتا (مثلاً NWS-001) ذخیره می‌شه
تا بعداً وقتی کاربر می‌نویسه "بررسی معامله NWS-001 ..."، بشه دوباره پیداش کرد.
"""

import sqlite3
import json
from datetime import datetime, timedelta
from config import DB_PATH


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS analyses (
            code TEXT PRIMARY KEY,
            created_at TEXT,
            coin TEXT,
            data TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            user_id INTEGER,
            coin TEXT,
            binance_symbol TEXT,
            added_at TEXT,
            PRIMARY KEY (user_id, coin)
        )
    """)
    # شمارنده‌ی مستقل برای تولید کد — با پاک‌سازی رکوردهای قدیمی هیچ‌وقت کم نمی‌شه،
    # پس هیچ‌وقت کد تکراری تولید نمی‌کنه.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS counters (
            name TEXT PRIMARY KEY,
            value INTEGER
        )
    """)
    cur.execute("INSERT OR IGNORE INTO counters (name, value) VALUES ('analysis_seq', 0)")

    # تنظیمات شخصی هر کاربر: تقویم (شمسی/میلادی)، منطقه زمانی، واحد پول
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            calendar TEXT DEFAULT 'gregorian',
            timezone TEXT DEFAULT 'Asia/Tehran',
            currency TEXT DEFAULT 'USD',
            toman_rate REAL
        )
    """)

    # مهاجرت امن: اگه دیتابیس قدیمی این ستون رو نداشت، اضافه‌ش کن (بدون خراب‌کردن داده‌ی موجود)
    cur.execute("PRAGMA table_info(user_settings)")
    existing_columns = {row[1] for row in cur.fetchall()}
    if "meme_focus_enabled" not in existing_columns:
        cur.execute("ALTER TABLE user_settings ADD COLUMN meme_focus_enabled INTEGER DEFAULT 0")

    # شهرهای/منطقه‌های زمانی که کاربرها اضافه کردن (برای انتخاب همه)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS custom_timezones (
            city_name TEXT PRIMARY KEY,
            tz_name TEXT
        )
    """)

    # معاملات در حال پیگیری — برای این‌که بعد از ری‌استارت ربات هم گم نشن
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tracked_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            user_id INTEGER,
            chat_id INTEGER,
            track_at TEXT,
            done INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)

    # خبرهایی که قبلاً دیده و فرستاده شدن — تو دیتابیس، نه فقط حافظه، که با
    # ری‌استارت ربات پاک نشه و باعث تکراری اومدن خبر نشه.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS seen_news (
            news_id TEXT PRIMARY KEY,
            seen_at TEXT
        )
    """)

    # نمادهای شناخته‌شده‌ی Binance — برای تشخیص لیستینگ‌های جدید (میم‌کوین‌های
    # تازه‌وارد و غیره). دفعه‌ی اول که پر می‌شه، هیچ اعلانی نمی‌ره (چون همه‌چی
    # «جدید» به‌نظر می‌رسه)، فقط از اون به بعد واقعاً نمادهای تازه رو می‌گیریم.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS known_symbols (
            symbol TEXT PRIMARY KEY,
            first_seen TEXT
        )
    """)

    # آخرین باری که یه میم‌کوین «داغ» اعلام شده — که هر ۱۵ دقیقه دوباره برای
    # همون کوین هشدار نفرستیم (فقط وقتی یه مدت گذشته و بازم داغه).
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hot_coin_alerts (
            symbol TEXT PRIMARY KEY,
            last_alert_at TEXT
        )
    """)

    conn.commit()

    # --- مهاجرت: اگه دیتابیس قدیمی‌ای وجود داره که واچ‌لیستش سراسری بوده (ستون user_id نداشته)،
    # خودکار به ساختار جدید (واچ‌لیست شخصی هر کاربر) تبدیلش می‌کنیم، بدون از دست رفتن داده. ---
    cur.execute("PRAGMA table_info(watchlist)")
    columns = [row[1] for row in cur.fetchall()]

    if columns and "user_id" not in columns:
        print("[مهاجرت دیتابیس] ساختار قدیمی واچ‌لیست پیدا شد — در حال تبدیل به واچ‌لیست شخصی...")

        cur.execute("ALTER TABLE watchlist RENAME TO watchlist_old_backup")
        cur.execute("""
            CREATE TABLE watchlist (
                user_id INTEGER,
                coin TEXT,
                binance_symbol TEXT,
                added_at TEXT,
                PRIMARY KEY (user_id, coin)
            )
        """)

        # ارزهای قدیمی رو به کاربر اصلی (TELEGRAM_CHAT_ID) نسبت می‌دیم که چیزی گم نشه
        try:
            from config import TELEGRAM_CHAT_ID
            if TELEGRAM_CHAT_ID and TELEGRAM_CHAT_ID.strip().lstrip("-").isdigit():
                primary_user = int(TELEGRAM_CHAT_ID)
                cur.execute("SELECT coin, binance_symbol, added_at FROM watchlist_old_backup")
                old_rows = cur.fetchall()
                for coin, symbol, added_at in old_rows:
                    cur.execute(
                        "INSERT OR IGNORE INTO watchlist (user_id, coin, binance_symbol, added_at) VALUES (?, ?, ?, ?)",
                        (primary_user, coin, symbol, added_at),
                    )
                print(f"[مهاجرت دیتابیس] {len(old_rows)} ارز قدیمی به کاربر اصلی منتقل شد.")
        except Exception as e:
            print(f"[مهاجرت دیتابیس] هشدار: نتونستم ارزهای قدیمی رو منتقل کنم ({e}) — واچ‌لیست همه از صفر شروع می‌شه.")

        cur.execute("DROP TABLE watchlist_old_backup")
        conn.commit()
        print("[مهاجرت دیتابیس] تموم شد ✅")

    conn.close()


def seed_watchlist_if_empty(default_coins: dict, user_id: int):
    """اگه واچ‌لیست این کاربر خالیه، با چندتا ارز پیش‌فرض پرش می‌کنه (فقط بار اول)."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM watchlist WHERE user_id = ?", (user_id,))
    count = cur.fetchone()[0]
    if count == 0:
        for coin, symbol in default_coins.items():
            cur.execute(
                "INSERT OR IGNORE INTO watchlist (user_id, coin, binance_symbol, added_at) VALUES (?, ?, ?, ?)",
                (user_id, coin, symbol, datetime.utcnow().isoformat()),
            )
        conn.commit()
    conn.close()


def get_watchlist(user_id: int):
    """برمی‌گردونه: دیکشنری {coin: binance_symbol} مخصوص همون کاربر"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT coin, binance_symbol FROM watchlist WHERE user_id = ?", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return {coin: symbol for coin, symbol in rows}


def add_to_watchlist(user_id, coin, binance_symbol):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO watchlist (user_id, coin, binance_symbol, added_at) VALUES (?, ?, ?, ?)",
        (user_id, coin, binance_symbol, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def remove_from_watchlist(user_id, coin):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM watchlist WHERE user_id = ? AND coin = ?", (user_id, coin))
    removed = cur.rowcount > 0
    conn.commit()
    conn.close()
    return removed


def get_next_code():
    """
    تولید کد بعدی به فرم NWS-001, NWS-002, ...
    از یه شمارنده‌ی مستقل استفاده می‌کنه (نه شمارش رکوردهای فعلی)، برای همین
    حتی بعد از پاک‌سازی رکوردهای قدیمی، کد تکراری تولید نمی‌شه.

    به‌عنوان یه لایه‌ی محافظتی اضافه، قبل از برگردوندن کد، چک می‌کنه که واقعاً
    تو جدول analyses وجود نداره — اگه به هر دلیلی (مثلاً دستکاری دستی دیتابیس)
    همون کد از قبل موجود بود، شمارنده رو جلو می‌بره تا به یه کد آزاد برسه.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        while True:
            cur.execute("UPDATE counters SET value = value + 1 WHERE name = 'analysis_seq'")
            cur.execute("SELECT value FROM counters WHERE name = 'analysis_seq'")
            next_num = cur.fetchone()[0]
            code = f"NWS-{next_num:03d}"

            cur.execute("SELECT 1 FROM analyses WHERE code = ?", (code,))
            if cur.fetchone() is None:
                conn.commit()
                return code
            # این کد از قبل وجود داره (نباید عادی پیش بیاد) — دوباره تلاش کن با عدد بعدی
    finally:
        conn.close()


def save_analysis(code, coin, data: dict):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO analyses (code, created_at, coin, data) VALUES (?, ?, ?, ?)",
        (code, datetime.utcnow().isoformat(), coin, json.dumps(data, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()


def get_analysis(code):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT coin, data FROM analyses WHERE code = ?", (code,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    coin, data_json = row
    return {"coin": coin, **json.loads(data_json)}


def count_analyses_older_than(days):
    """چند تا رکورد قدیمی‌تر از N روز هست — برای نمایش پیش از پاک‌سازی."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    cur.execute("SELECT COUNT(*) FROM analyses WHERE created_at < ?", (cutoff,))
    count = cur.fetchone()[0]
    conn.close()
    return count


def delete_analyses_older_than(days):
    """پاک کردن واقعی رکوردهای قدیمی‌تر از N روز. تعداد پاک‌شده رو برمی‌گردونه."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    cur.execute("DELETE FROM analyses WHERE created_at < ?", (cutoff,))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return deleted


# ============== تنظیمات کاربر ==============

_DEFAULT_SETTINGS = {"calendar": "gregorian", "timezone": "Asia/Tehran", "currency": "USD", "toman_rate": None}


def get_user_settings(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT calendar, timezone, currency, toman_rate FROM user_settings WHERE user_id = ?",
        (user_id,),
    )
    row = cur.fetchone()
    conn.close()
    if row is None:
        return dict(_DEFAULT_SETTINGS)
    calendar, timezone, currency, toman_rate = row
    return {"calendar": calendar, "timezone": timezone, "currency": currency, "toman_rate": toman_rate}


def update_user_settings(user_id, **kwargs):
    """فقط فیلدهایی که پاس داده بشن آپدیت می‌شن، بقیه دست‌نخورده می‌مونن."""
    current = get_user_settings(user_id)
    current.update({k: v for k, v in kwargs.items() if v is not None})

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO user_settings (user_id, calendar, timezone, currency, toman_rate)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            calendar=excluded.calendar,
            timezone=excluded.timezone,
            currency=excluded.currency,
            toman_rate=excluded.toman_rate
        """,
        (user_id, current["calendar"], current["timezone"], current["currency"], current["toman_rate"]),
    )
    conn.commit()
    conn.close()


def add_custom_timezone(city_name, tz_name):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO custom_timezones (city_name, tz_name) VALUES (?, ?)",
        (city_name, tz_name),
    )
    conn.commit()
    conn.close()


def get_all_timezones():
    """لیست کامل شهرهای قابل‌انتخاب: تهران (همیشگی) + هرچی کاربرها اضافه کردن."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT city_name, tz_name FROM custom_timezones")
    rows = cur.fetchall()
    conn.close()
    result = {"تهران": "Asia/Tehran"}
    result.update({city: tz for city, tz in rows})
    return result


# ============== پیگیری معاملات ==============

def save_tracked_trade(code, user_id, chat_id, track_at_iso, start_time_iso=None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO tracked_trades (code, user_id, chat_id, track_at, created_at) VALUES (?, ?, ?, ?, ?)",
        (code, user_id, chat_id, track_at_iso, start_time_iso or datetime.utcnow().isoformat()),
    )
    conn.commit()
    tracked_id = cur.lastrowid
    conn.close()
    return tracked_id


def get_pending_tracked_trades():
    """همه‌ی پیگیری‌های هنوز انجام‌نشده — برای زمان‌بندی دوباره بعد از ری‌استارت ربات."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, code, user_id, chat_id, track_at, created_at FROM tracked_trades WHERE done = 0")
    rows = cur.fetchall()
    conn.close()
    return [
        {"id": r[0], "code": r[1], "user_id": r[2], "chat_id": r[3], "track_at": r[4], "created_at": r[5]}
        for r in rows
    ]


def mark_tracked_trade_done(tracked_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE tracked_trades SET done = 1 WHERE id = ?", (tracked_id,))
    conn.commit()
    conn.close()


# ============== خبرهای دیده‌شده (جلوگیری از تکرار، ری‌استارت‌مقاوم) ==============

def is_news_seen(news_id):
    if not news_id:
        return False
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM seen_news WHERE news_id = ?", (news_id,))
    row = cur.fetchone()
    conn.close()
    return row is not None


def mark_news_seen(news_id):
    if not news_id:
        return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO seen_news (news_id, seen_at) VALUES (?, ?)",
        (news_id, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def cleanup_old_seen_news(days=14):
    """خبرهای دیده‌شده‌ی خیلی قدیمی رو پاک می‌کنه که جدول بی‌نهایت بزرگ نشه."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    cur.execute("DELETE FROM seen_news WHERE seen_at < ?", (cutoff,))
    conn.commit()
    conn.close()


# ============== نمادهای شناخته‌شده (تشخیص لیستینگ جدید) ==============

def get_known_symbols():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT symbol FROM known_symbols")
    rows = cur.fetchall()
    conn.close()
    return set(r[0] for r in rows)


def add_known_symbols(symbols):
    if not symbols:
        return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    cur.executemany(
        "INSERT OR IGNORE INTO known_symbols (symbol, first_seen) VALUES (?, ?)",
        [(s, now) for s in symbols],
    )
    conn.commit()
    conn.close()


def known_symbols_count():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM known_symbols")
    count = cur.fetchone()[0]
    conn.close()
    return count


def get_recently_known_symbols(days=3):
    """نمادهایی که اخیراً (چند روز گذشته) برای اولین‌بار دیده شدن — یعنی لیستینگ‌های تازه."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    cur.execute("SELECT symbol FROM known_symbols WHERE first_seen >= ?", (cutoff,))
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


# ============== تمرکز روی میم‌کوین‌های داغ (روشن/خاموش شخصی هر کاربر) ==============

def get_meme_focus_enabled(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT meme_focus_enabled FROM user_settings WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return bool(row[0]) if row else False


def toggle_meme_focus(user_id):
    """وضعیت رو برعکس می‌کنه (اگه خاموش بود روشن، اگه روشن بود خاموش) و وضعیت جدید رو برمی‌گردونه."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)", (user_id,))
    cur.execute("SELECT meme_focus_enabled FROM user_settings WHERE user_id = ?", (user_id,))
    current = bool(cur.fetchone()[0])
    new_value = 0 if current else 1
    cur.execute("UPDATE user_settings SET meme_focus_enabled = ? WHERE user_id = ?", (new_value, user_id))
    conn.commit()
    conn.close()
    return bool(new_value)


def get_meme_focus_users(all_user_ids):
    """از بین همه‌ی کاربرهای مجاز، فقط اونایی که تمرکز میم‌کوین رو روشن کردن."""
    if not all_user_ids:
        return []
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    placeholders = ",".join("?" * len(all_user_ids))
    cur.execute(
        f"SELECT user_id FROM user_settings WHERE user_id IN ({placeholders}) AND meme_focus_enabled = 1",
        list(all_user_ids),
    )
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


def can_send_hot_alert(symbol, cooldown_hours=6):
    """آیا برای این کوین، به‌قدر کافی از آخرین هشدار «داغ» گذشته که دوباره بفرستیم؟"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT last_alert_at FROM hot_coin_alerts WHERE symbol = ?", (symbol,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        return True
    try:
        last_alert = datetime.fromisoformat(row[0])
    except Exception:
        return True
    return datetime.utcnow() - last_alert >= timedelta(hours=cooldown_hours)


def mark_hot_alert_sent(symbol):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO hot_coin_alerts (symbol, last_alert_at) VALUES (?, ?) "
        "ON CONFLICT(symbol) DO UPDATE SET last_alert_at = excluded.last_alert_at",
        (symbol, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
