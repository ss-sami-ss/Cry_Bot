# -*- coding: utf-8 -*-
"""
سیستم امتیاز ترکیبی (Confluence).
هر اندیکاتور به‌تنهایی قابل‌اعتماد نیست؛ وقتی چندتاشون هم‌جهت باشن اطمینان
به هشدار بیشتر می‌شه. این ماژول این سیگنال‌ها رو می‌شمره و یه جمله‌ی ساده‌ی
خلاصه می‌سازه — نه پیش‌بینی قطعی.

نکته‌ی مهم (بعد از تحلیل ۷۸۷۵ ردیف داده‌ی واقعی ۳۰ روزه): تو بازار در حالت
روند واقعی (Trending)، اکثر سیگنال‌های «برگشت به میانگین» (RSI بالا، Fear&Greed
افراطی، نسبت لانگ/شورت، نزدیکی به حمایت/مقاومت) دقیقاً برعکس عمل می‌کنن —
یعنی RSI بالا تو روند، نشونه‌ی ادامه‌ی رشده، نه هشدار برگشت. برای همین این
سیگنال‌ها الان به رژیم بازار (روند/رنج) وابسته‌ان: تو رنج از منطق «برگشت به
میانگین» استفاده می‌کنن (تئوری کلاسیک، هنوز رو داده‌ی رنج تستش نکردیم)،
تو روند از منطق «ادامه‌ی روند» (که رو داده‌ی واقعی تأیید شده).
"""

FUNDING_EXTREME_THRESHOLD_HIGH = 0.01  # صدک ۹۰ام داده‌ی واقعی (نه حدس کتابی ۰.۰۵ قدیمی)
FUNDING_EXTREME_THRESHOLD_LOW = -0.005  # صدک ۱۰ام داده‌ی واقعی
SR_PROXIMITY_THRESHOLD = 0.015  # ۱.۵٪ — چقدر نزدیک به حمایت/مقاومت یعنی «نزدیک»
OI_EXTREME_THRESHOLD = 10  # درصد تغییر پوزیشن‌های باز در ۲۴ ساعت
LS_RATIO_HIGH = 1.5  # نسبت لانگ/شورت بالای این عدد = اکثریت لانگ
LS_RATIO_LOW = 0.67  # پایین این عدد = اکثریت شورت
VOLUME_SPIKE_MULTIPLIER = 2.0  # حجم کندل آخر چند برابر میانگین باشه که «جهش» حساب بشه
MA_TREND_THRESHOLD_PERCENT = 1.0  # حداقل چند درصد از میانگین متحرک فاصله داشته باشه که معنی‌دار حساب بشه


def _rsi_flag(rsi, regime="RANGING", trend_direction=None):
    if rsi is None:
        return None

    if rsi >= 70:
        if regime == "TRENDING":
            # تأیید‌شده رو داده‌ی واقعی: تو روند صعودی، RSI بالا یعنی ادامه‌ی رشد (نه برگشت)
            kind = "cooled" if trend_direction == "UP" else "overheated"
            return (kind, "RSI بالا (تو روند، یعنی ادامه‌ی حرکت)")
        return ("overheated", "RSI اشباع خرید (تئوری برگشت به میانگین، رو رنج تست نشده)")

    if rsi <= 30:
        if regime == "TRENDING":
            kind = "overheated" if trend_direction == "UP" else "cooled"
            return (kind, "RSI پایین (تو روند، یعنی ادامه‌ی حرکت)")
        return ("cooled", "RSI اشباع فروش (تئوری برگشت به میانگین، رو رنج تست نشده)")

    return None


def _funding_flag(funding_rate_percent):
    if funding_rate_percent is None:
        return None
    if funding_rate_percent >= FUNDING_EXTREME_THRESHOLD_HIGH:
        return ("overheated", "فاندینگ مثبت بالا (ازدحام لانگ)")
    if funding_rate_percent <= FUNDING_EXTREME_THRESHOLD_LOW:
        return ("cooled", "فاندینگ منفی بالا (ازدحام شورت)")
    return None


def _fear_greed_flag(value, regime="RANGING", trend_direction=None):
    if value is None:
        return None

    if value >= 75:
        if regime == "TRENDING":
            kind = "cooled" if trend_direction == "UP" else "overheated"
            return (kind, "طمع شدید (تو روند صعودی، ادامه‌ی طبیعیه)")
        return ("overheated", "طمع شدید (تئوری برگشت، رو رنج تست نشده)")

    if value <= 25:
        # تأیید‌شده رو داده‌ی واقعی: ترس شدید معمولاً با افت بیشتر همراه بود، نه برگشت
        if regime == "TRENDING" and trend_direction == "DOWN":
            return ("overheated", "ترس شدید (تو روند نزولی، تأییدشده رو‌ی داده: افت بیشتر)")
        return ("overheated", "ترس شدید (رو داده‌ی واقعی، برخلاف تئوری، با افت بیشتر همراه بود)")

    return None


def _sr_proximity_flag(price, support, resistance, regime="RANGING", trend_direction=None):
    """
    نزدیکی قیمت به حمایت/مقاومت.

    تحلیل روی ۱۷,۰۰۰ ردیف داده‌ی واقعی (۱۰ ماه، رژیم‌های متنوع) نشون داد:
    برخلاف تئوری کلاسیک، نزدیکی به مقاومت هم — چه تو رنج (میانگین بازده +۰.۱۴٪ در
    برابر baseline خودِ رنج که -۰.۲۴٪ بود)، چه تو روند صعودی (+۰.۵۹٪ در برابر
    baseline +۰.۲۶٪) — قاطعانه با ادامه‌ی رشد (شکستن مقاومت) همراه بوده، نه برگشت.
    این آزمایش با چند آستانه‌ی مختلف (۰.۵٪ تا ۳٪) هم تکرار شد و نتیجه ثابت موند —
    پس این «ضعف آستانه» نبود، فرضیه‌ی اولیه اشتباه بود. برای همین الان نزدیکی به
    مقاومت هم مثل نزدیکی به حمایت، «cooled» (لانگ‌محور) در نظر گرفته می‌شه —
    مستقل از رژیم.
    """
    if price is None or price == 0:
        return None

    if resistance:
        dist_to_resistance = abs(resistance - price) / price
        if dist_to_resistance <= SR_PROXIMITY_THRESHOLD:
            return ("cooled", f"نزدیک مقاومت ({resistance}) — رو داده‌ی واقعی معمولاً شکسته می‌شه، نه برگشت")

    if support:
        dist_to_support = abs(price - support) / price
        if dist_to_support <= SR_PROXIMITY_THRESHOLD:
            return ("cooled", f"قیمت نزدیک حمایت ({support})")

    return None


def _oi_flag(oi_change_percent):
    """
    تغییر شدید پوزیشن‌های باز (Open Interest) در ۲۴ ساعت اخیر رو هم سیگنال در نظر می‌گیره:
    افزایش شدید → ورود پول اهرم‌دار جدید، ازدحام و آسیب‌پذیری بیشتر (هم‌جهت با شورت)
    کاهش شدید → بستن پوزیشن‌ها/تخلیه‌ی اهرم، معمولاً بعد از یه حرکت شدید (هم‌جهت با لانگ)
    """
    if oi_change_percent is None:
        return None
    if oi_change_percent >= OI_EXTREME_THRESHOLD:
        return ("overheated", f"افزایش شدید پوزیشن‌های باز (+{oi_change_percent}٪)")
    if oi_change_percent <= -OI_EXTREME_THRESHOLD:
        return ("cooled", f"کاهش شدید پوزیشن‌های باز ({oi_change_percent}٪)")
    return None


def _ls_ratio_flag(ratio, regime="RANGING", trend_direction=None):
    """
    نسبت حساب‌های لانگ به شورت. تو رنج طبق تئوری کلاسیک (ازدحام = هشدار برگشت).
    تو روند صعودی، داده‌ی واقعی نشون داد اکثریت لانگ معمولاً با ادامه‌ی رشد همراهه، نه اصلاح.
    """
    if ratio is None:
        return None

    if ratio >= LS_RATIO_HIGH:
        if regime == "TRENDING" and trend_direction == "UP":
            return ("cooled", f"اکثریت لانگ تو روند صعودی (تأییدشده: ادامه‌ی رشد)")
        return ("overheated", f"اکثریت حساب‌ها لانگ‌ان (نسبت {ratio})")

    if ratio <= LS_RATIO_LOW:
        if regime == "TRENDING" and trend_direction == "DOWN":
            return ("overheated", f"اکثریت شورت تو روند نزولی (رو داده تست نشده)")
        return ("cooled", f"اکثریت حساب‌ها شورت‌ان (نسبت {ratio})")

    return None


def _volume_spike_flag(volume_ratio, candle_direction):
    """جهش حجم روی یه کندل صعودی = تأیید صعود (لانگ‌محور)؛ روی نزولی = تأیید نزول (شورت‌محور)."""
    if volume_ratio is None or candle_direction is None:
        return None
    if volume_ratio >= VOLUME_SPIKE_MULTIPLIER:
        if candle_direction == "up":
            return ("cooled", f"جهش حجم در کندل صعودی (~{volume_ratio}× میانگین)")
        elif candle_direction == "down":
            return ("overheated", f"جهش حجم در کندل نزولی (~{volume_ratio}× میانگین)")
    return None


def _ma_trend_flag(ma_trend_percent):
    """فاصله‌ی معنی‌دار قیمت از میانگین متحرک — بالای میانگین = روند صعودی (لانگ‌محور)."""
    if ma_trend_percent is None:
        return None
    if ma_trend_percent >= MA_TREND_THRESHOLD_PERCENT:
        return ("cooled", f"قیمت بالای میانگین متحرک (+{ma_trend_percent}٪)")
    if ma_trend_percent <= -MA_TREND_THRESHOLD_PERCENT:
        return ("overheated", f"قیمت پایین میانگین متحرک ({ma_trend_percent}٪)")
    return None


def _all_flags(rsi, funding_rate_percent, fear_greed_value, price=None, support=None, resistance=None,
               oi_change_percent=None, ls_ratio=None, volume_ratio=None, volume_direction=None, ma_trend_percent=None,
               extra_flags=None, regime="RANGING", trend_direction=None):
    flags = [
        _rsi_flag(rsi, regime, trend_direction),
        _funding_flag(funding_rate_percent),
        _fear_greed_flag(fear_greed_value, regime, trend_direction),
    ]
    if price is not None:
        flags.append(_sr_proximity_flag(price, support, resistance, regime, trend_direction))
    if oi_change_percent is not None:
        flags.append(_oi_flag(oi_change_percent))
    if ls_ratio is not None:
        flags.append(_ls_ratio_flag(ls_ratio, regime, trend_direction))
    if volume_ratio is not None:
        flags.append(_volume_spike_flag(volume_ratio, volume_direction))
    if ma_trend_percent is not None:
        flags.append(_ma_trend_flag(ma_trend_percent))
    if extra_flags:
        flags.extend(extra_flags)
    return flags


def decide_direction_and_alignment(rsi, funding_rate_percent, fear_greed_value, price=None, support=None, resistance=None,
                                    oi_change_percent=None, ls_ratio=None, volume_ratio=None, volume_direction=None, ma_trend_percent=None,
                                    extra_flags=None, regime="RANGING", trend_direction=None):
    """
    تشخیص جهت معامله (لانگ/شورت) بر پایه‌ی هم‌جهتی سیگنال‌ها (نه فقط RSI تنها).
    تا ۱۱ سیگنال ممکنه دخیل باشن: ۸ تای فنی/بازار + ۳ تکنیک (عدد رند، چند تایم‌فریم، شکست‌وتست).

    regime/trend_direction: نتیجه‌ی calculate_market_regime — چون تحلیل روی داده‌ی واقعی نشون داد
    خیلی از سیگنال‌ها تو حالت «روند واقعی» برعکس عمل می‌کنن (نگاه کن به داکیومنت بالای فایل).

    منطق: اگه اکثریت سیگنال‌های موجود «داغ/اشباع‌خرید» باشن → شورت
          اگه اکثریت «سرد/اشباع‌فروش» باشن → لانگ
          در تساوی یا نبود سیگنال → پیش‌فرض لانگ

    برمی‌گردونه: (direction, aligned_count, total_signals)
    """
    flags = _all_flags(rsi, funding_rate_percent, fear_greed_value, price, support, resistance,
                        oi_change_percent, ls_ratio, volume_ratio, volume_direction, ma_trend_percent, extra_flags,
                        regime, trend_direction)
    total_signals = len(flags)
    available = [f for f in flags if f is not None]

    overheated_count = sum(1 for kind, _ in available if kind == "overheated")
    cooled_count = sum(1 for kind, _ in available if kind == "cooled")

    if overheated_count > cooled_count:
        return "SHORT", overheated_count, total_signals
    elif cooled_count > overheated_count:
        return "LONG", cooled_count, total_signals
    else:
        return "LONG", max(overheated_count, cooled_count), total_signals


def build_confluence_summary(rsi, funding_rate_percent, fear_greed_value, price=None, support=None, resistance=None,
                              oi_change_percent=None, ls_ratio=None, volume_ratio=None, volume_direction=None, ma_trend_percent=None,
                              extra_flags=None, regime="RANGING", trend_direction=None):
    """
    خروجی: یه جمله‌ی ساده که تعداد سیگنال‌های هم‌جهت رو خلاصه می‌کنه.
    آستانه‌ها اینجا هم **نسبتی**ان (نه عدد خام)، دقیقاً هم‌راستا با build_strength_bar_from_alignment
    — که رنگ این جمله همیشه با رنگ نوار قدرت سیگنال یکی باشه، نه ناهماهنگ.
    """
    flags = _all_flags(rsi, funding_rate_percent, fear_greed_value, price, support, resistance,
                        oi_change_percent, ls_ratio, volume_ratio, volume_direction, ma_trend_percent, extra_flags,
                        regime, trend_direction)
    total = len(flags)
    available = [f for f in flags if f is not None]

    overheated = [label for kind, label in available if kind == "overheated"]
    cooled = [label for kind, label in available if kind == "cooled"]

    overheated_ratio = len(overheated) / total if total else 0
    cooled_ratio = len(cooled) / total if total else 0

    if overheated_ratio >= 0.5:
        return (
            f"🔴 نتیجه کلی: {len(overheated)} از {total} سیگنال هم‌جهت نشون‌دهنده‌ی بازار داغ/اشباع‌خرید هستن "
            f"({'، '.join(overheated)}) → احتمال اصلاح قیمت افزایش یافته، احتیاط در ورود جدید"
        )
    elif cooled_ratio >= 0.5:
        return (
            f"🟢 نتیجه کلی: {len(cooled)} از {total} سیگنال هم‌جهت نشون‌دهنده‌ی بازار سرد/اشباع‌فروش هستن "
            f"({'، '.join(cooled)}) → احتمال بازگشت قیمت افزایش یافته"
        )
    elif overheated or cooled:
        only = (overheated or cooled)[0]
        return f"🟡 نتیجه کلی: فقط {len(overheated)+len(cooled)} از {total} سیگنال ({only}) هشدار می‌ده، بقیه عادی‌ان → وضعیت هنوز شفاف نیست"
    else:
        return "⚪ نتیجه کلی: در حال حاضر هیچ سیگنال هشداردهنده‌ای دیده نمی‌شه، بازار در وضعیت عادی به‌نظر می‌رسه"


# تعداد تکرار ایموجی برای ساخت یه نوار که تقریباً کل عرض پیام تلگرام رو بگیره
_BAR_WIDTH = 20

# آستانه‌ی نسبت هم‌جهتی (نه عدد خام) که از این به بعد «سیگنال خیلی قوی» حساب بشه و ستاره بگیره —
# چون تعداد کل سیگنال‌ها (۸ تا ۱۱) متغیره، نسبت درصدی منصفانه‌تر از عدد ثابته.
STAR_THRESHOLD_RATIO = 0.75  # معادل «۶ از ۸» که خودت گفتی


def build_strength_bar_from_alignment(aligned_count, total_signals=3):
    """
    نسخه‌ی مشترک — از همون aligned_count/total_signals که decide_direction_and_alignment
    برگردونده استفاده می‌کنه، تا رنگ نوار همیشه دقیقاً با جهت انتخاب‌شده هماهنگ باشه.

    نسبت رو به درصد تبدیل می‌کنه (نه عدد خام) که چه ۸ سیگنال باشه چه ۱۱، منصفانه بمونه:
      🟢⭐ ≥ ۷۵٪ سیگنال‌ها هم‌جهت‌ان (خیلی واضح — ستاره می‌گیره که کاملاً معلوم باشه)
      🟠 ۵۰٪ سیگنال‌ها هم‌جهت‌ان (نسبتاً خوب)
      🔴 کمتر از ۵۰٪ (ضعیف یا ضدونقیض)
    """
    ratio = aligned_count / total_signals if total_signals else 0

    if ratio >= STAR_THRESHOLD_RATIO:
        emoji, label = "🟢", "سیگنال بسیار قوی و واضح — اکثر نشونه‌ها هم‌جهت‌ان"
        star = "⭐ "
    elif ratio >= 0.5:
        emoji, label = "🟠", "نشونه‌های نسبتاً خوب — ولی کامل نیست"
        star = ""
    else:
        emoji, label = "🔴", "نشونه‌های ضعیف یا ضدونقیض — احتیاط بیشتر"
        star = ""

    bar = emoji * _BAR_WIDTH
    return f"{star}{bar}{star}\n{star}{label} ({aligned_count}/{total_signals}){star}"


def build_strength_bar(rsi, funding_rate_percent, fear_greed_value, price=None, support=None, resistance=None,
                        oi_change_percent=None, ls_ratio=None, volume_ratio=None, volume_direction=None, ma_trend_percent=None,
                        extra_flags=None, regime="RANGING", trend_direction=None):
    """نسخه‌ی مستقل (بدون جهت از بیرون) — برای جاهایی که فقط رنگ لازمه، نه جهت."""
    _, aligned_count, total = decide_direction_and_alignment(rsi, funding_rate_percent, fear_greed_value, price, support, resistance,
                                                               oi_change_percent, ls_ratio, volume_ratio, volume_direction, ma_trend_percent,
                                                               extra_flags, regime, trend_direction)
    return build_strength_bar_from_alignment(aligned_count, total)


def entry_timing_verdict(aligned_count, total_signals, direction):
    """
    یه جواب مستقیم به «الان زمان مناسبیه؟» — بر پایه‌ی همون نسبت هم‌جهتی سیگنال‌ها
    که برای رنگ نوار هم استفاده می‌شه (پس همیشه با هم هماهنگن).
    """
    direction_fa = "لانگ (خرید)" if direction == "LONG" else "شورت (فروش)"
    ratio = aligned_count / total_signals if total_signals else 0

    if ratio >= 0.75:
        return (
            f"✅ بر اساس سیگنال‌های فعلی، شرایط برای ورود {direction_fa} نسبتاً واضح و مناسب به‌نظر می‌رسه — "
            f"البته مثل همیشه، تصمیم و ریسکش با خودته."
        )
    elif ratio >= 0.5:
        return (
            f"🟡 سیگنال‌ها تا حدی از {direction_fa} حمایت می‌کنن ولی کامل نیستن — "
            f"اگه وارد می‌شی، شاید بهتر باشه با حجم کمتر و احتیاط بیشتر باشه."
        )
    else:
        return (
            "🔴 در حال حاضر سیگنال قوی یا واضحی برای ورود دیده نمی‌شه — "
            "شاید صبر کردن برای یه موقعیت روشن‌تر منطقی‌تر باشه."
        )
