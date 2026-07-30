@echo off
REM ============================================================
REM  NEBULA Stock Analysis — ดับเบิลคลิกไฟล์นี้แล้วใช้งานได้เลย
REM  สร้าง venv (ครั้งแรก) + ติดตั้ง dependencies + สร้าง .env + เปิดเบราว์เซอร์
REM ============================================================
cd /d "%~dp0"
title NEBULA Stock Analysis
chcp 65001 >nul

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo [!] ไม่พบ Python บนเครื่องนี้
  echo     ติดตั้งจาก https://www.python.org/downloads/ แล้วตอนติดตั้ง
  echo     ให้ติ๊ก "Add python.exe to PATH" ด้วย จากนั้นเปิดไฟล์นี้อีกครั้ง
  echo.
  pause
  exit /b 1
)

if not exist "venv\" (
  echo [1/4] กำลังสร้าง virtual environment ... ^(ครั้งแรกใช้เวลาสักครู่^)
  python -m venv venv
  if errorlevel 1 (
    echo [!] สร้าง venv ไม่สำเร็จ
    pause
    exit /b 1
  )
)

echo [2/4] กำลังติดตั้ง/ตรวจสอบ dependencies ...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul 2>nul
pip install -q -r requirements.txt
if errorlevel 1 (
  echo [!] ติดตั้ง dependencies ไม่สำเร็จ — ตรวจอินเทอร์เน็ตแล้วลองอีกครั้ง
  pause
  exit /b 1
)

if not exist ".env" (
  echo [3/4] สร้างไฟล์ตั้งค่า .env ให้อัตโนมัติ ...
  copy /y ".env.example" ".env" >nul
  echo       ^(ตั้งค่าให้เชื่อมระบบเทรด MT5 ที่ 127.0.0.1:8641 ไว้แล้ว^)
) else (
  echo [3/4] พบไฟล์ .env อยู่แล้ว — ใช้ค่าเดิม
)

echo [4/4] กำลังเปิดแอป ...
echo.
echo    ========================================================
echo      NEBULA พร้อมใช้งานที่   http://127.0.0.1:5000
echo      เบราว์เซอร์จะเปิดให้เองใน 6 วินาที
echo      ปิดโปรแกรม: กด Ctrl+C ในหน้าต่างนี้
echo    ========================================================
echo.
echo    เมนู "พอร์ต MT5" จะมีข้อมูลเมื่อ volume-edge เปิดอยู่ที่ port 8641
echo.

start "" /b cmd /c "timeout /t 6 >nul & start http://127.0.0.1:5000"
python app.py

echo.
echo แอปหยุดทำงานแล้ว
pause
