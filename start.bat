@echo off
REM ============================================================
REM  NEBULA Stock Analysis — ดับเบิลคลิกไฟล์นี้แล้วใช้งานได้เลย
REM  สร้าง venv (ครั้งแรก) + ติดตั้ง dependencies + สร้าง .env + เปิดเบราว์เซอร์
REM ============================================================
chcp 65001 >nul 2>nul
cd /d "%~dp0"
title NEBULA Stock Analysis

REM ---------- หา Python ----------
REM ใช้ตัวเรียก py ก่อน เพราะเชื่อถือได้กว่า python (ที่อาจเป็น alias ของ Microsoft Store)
set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY (
  python --version >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo.
  echo   [!] ไม่พบ Python บนเครื่องนี้
  echo.
  echo   วิธีแก้: ติดตั้งจาก https://www.python.org/downloads/
  echo            ตอนติดตั้งให้ติ๊ก "Add python.exe to PATH" ด้วย
  echo            แล้วปิดหน้าต่างนี้ เปิด start.bat อีกครั้ง
  echo.
  pause
  exit /b 1
)

REM ---------- venv ----------
if not exist "venv\Scripts\python.exe" (
  echo [1/4] สร้าง virtual environment ... ^(ครั้งแรกใช้เวลาสักครู่^)
  %PY% -m venv venv
  if not exist "venv\Scripts\python.exe" (
    echo   [!] สร้าง venv ไม่สำเร็จ — ลองรันคำสั่งนี้เองเพื่อดู error:
    echo       %PY% -m venv venv
    pause
    exit /b 1
  )
) else (
  echo [1/4] พบ virtual environment แล้ว
)

set "VPY=venv\Scripts\python.exe"

REM ---------- dependencies ----------
echo [2/4] ตรวจ/ติดตั้ง dependencies ...
"%VPY%" -m pip install --upgrade pip >nul 2>nul
"%VPY%" -m pip install -q -r requirements.txt
if errorlevel 1 (
  echo.
  echo   [!] ติดตั้ง dependencies ไม่สำเร็จ
  echo       ตรวจอินเทอร์เน็ตแล้วเปิด start.bat อีกครั้ง
  echo       ถ้ายังไม่ได้ ลองรัน: "%VPY%" -m pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)

REM ---------- ไฟล์ตั้งค่า ----------
if not exist ".env" (
  echo [3/4] สร้างไฟล์ตั้งค่า .env ให้อัตโนมัติ
  copy /y ".env.example" ".env" >nul
  echo       ตั้งให้เชื่อมระบบเทรด MT5 ที่ 127.0.0.1:8641 ไว้แล้ว
) else (
  echo [3/4] พบไฟล์ .env อยู่แล้ว — ใช้ค่าเดิม
)

REM ---------- เปิดแอป ----------
echo [4/4] เปิดแอป ...
echo.
echo   ==========================================================
echo     NEBULA พร้อมใช้งานที่    http://127.0.0.1:5000
echo     เบราว์เซอร์จะเปิดให้เองใน 7 วินาที
echo     ปิดโปรแกรม: กด Ctrl+C ในหน้าต่างนี้
echo   ==========================================================
echo.
echo   เมนู "พอร์ต MT5" จะมีข้อมูลเมื่อ volume-edge เปิดอยู่ที่ port 8641
echo.

REM รอให้เซิร์ฟเวอร์พร้อมก่อนเปิดเบราว์เซอร์ (ใช้ ping แทน timeout เพราะทำงานได้ทุกกรณี)
start "" /b cmd /c "ping -n 8 127.0.0.1 >nul & start "" http://127.0.0.1:5000"

"%VPY%" app.py

echo.
echo แอปหยุดทำงานแล้ว
pause
