# -*- coding: utf-8 -*-
"""
ترجمه‌ی خلاصه‌ی خبر به فارسی. چون سرویس‌های ترجمه‌ی رایگان گاهی قطع/کند می‌شن،
چند موتور مختلف رو به‌ترتیب امتحان می‌کنه:
  ۱) Google (از طریق کتابخونه‌ی deep-translator)
  ۲) MyMemory (از طریق همون کتابخونه)
  ۳) MyMemory با درخواست مستقیم HTTP (بدون وابستگی به کتابخونه — قوی‌ترین فال‌بک)
نتیجه‌ی هر خبر کش می‌شه که برای چند کاربر/چند بار دوباره ترجمه نشه.
اگه همه‌ی موتورها شکست بخورن، متن اصلی انگلیسی همراه با یه علامت "(ترجمه نشد)" برمی‌گرده.
"""

import requests

_translation_cache = {}


def _try_google(text):
    from deep_translator import GoogleTranslator
    return GoogleTranslator(source="en", target="fa").translate(text)


def _try_mymemory_lib(text):
    from deep_translator import MyMemoryTranslator
    return MyMemoryTranslator(source="en-GB", target="fa-IR").translate(text)


def _try_mymemory_direct(text):
    """درخواست مستقیم به API رایگان MyMemory، بدون نیاز به کتابخونه‌ی جانبی."""
    resp = requests.get(
        "https://api.mymemory.translated.net/get",
        params={"q": text, "langpair": "en|fa"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    translated = data.get("responseData", {}).get("translatedText")
    if not translated:
        raise ValueError("پاسخ MyMemory خالی بود")
    return translated


def translate_to_persian(text, cache_key=None):
    """
    text: متن انگلیسی (عنوان یا توضیح خبر)
    cache_key: یه شناسه‌ی یکتا (مثلاً آیدی خبر) برای کش کردن — اگه ندی، خودِ متن کلید می‌شه
    """
    if not text:
        return text

    key = cache_key or text
    if key in _translation_cache:
        return _translation_cache[key]

    trimmed = text[:400]
    translated = None

    engines = [
        ("Google", _try_google),
        ("MyMemory (کتابخونه)", _try_mymemory_lib),
        ("MyMemory (مستقیم)", _try_mymemory_direct),
    ]

    for engine_name, engine_func in engines:
        try:
            result = engine_func(trimmed)
            if result and result.strip() and result.strip() != trimmed.strip():
                translated = result
                print(f"[ترجمه] موفق با موتور {engine_name}")
                break
        except Exception as e:
            print(f"[هشدار ترجمه] موتور {engine_name} جواب نداد: {type(e).__name__}: {e}")

    if not translated:
        print("[هشدار ترجمه] هیچ‌کدوم از ۳ موتور جواب ندادن — احتمالاً مشکل از اتصال اینترنت یا فایروال سیستمه.")
        translated = f"{text}\n(⚠️ ترجمه در دسترس نبود)"

    _translation_cache[key] = translated
    return translated
