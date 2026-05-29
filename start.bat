@echo off
REM ============================================================
REM  NEBULA Stock Analysis - ตัวช่วยรันบน Windows
REM  สร้าง venv (ครั้งแรก) + ติดตั้ง dependencies + รันแอป
REM ============================================================
cd /d "%~dp0"
title NEBULA Stock Analysis

if not exist "venv\" (
  echo [1/3] กำลังสร้าง virtual environment ...
  python -m venv venv
)

echo [2/3] กำลังติดตั้ง/ตรวจสอบ dependencies ...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
pip install -r requirements.txt

echo [3/3] กำลังเปิดแอป ที่ http://127.0.0.1:5000
echo.
python app.py

pause
