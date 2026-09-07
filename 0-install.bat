@echo off
chcp 65001 >nul
echo ========================================
echo   نصب پکیج‌های لازم برای ربات
echo ========================================
echo.

echo در حال آپدیت pip...
python -m pip install --upgrade pip

echo.
echo در حال نصب کتابخونه‌ها...
pip install -r requirements.txt

echo.
echo ========================================
echo   نصب تمام شد!
echo   حالا فایل "1-set-tokens.bat" رو باز کن
echo   و توکن‌های خودت رو توش بذار.
echo ========================================
pause
