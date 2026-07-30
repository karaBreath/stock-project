@echo off
REM ============================================================
REM  NEBULA — ดึงเวอร์ชันใหม่จาก GitHub แล้วเปิดใช้งานต่อ
REM  ดับเบิลคลิกไฟล์นี้เวลาต้องการอัปเดตโค้ด
REM ============================================================
chcp 65001 >nul 2>nul
cd /d "%~dp0"
title NEBULA — อัปเดต

set "BRANCH=claude/stock-trading-project-zjrrcz"

where git >nul 2>nul
if errorlevel 1 (
  echo.
  echo   [!] ไม่พบ git บนเครื่องนี้ — ติดตั้งจาก https://git-scm.com/download/win
  echo.
  pause
  exit /b 1
)

echo กำลังดึงเวอร์ชันใหม่จาก branch %BRANCH% ...
git pull origin %BRANCH%
if errorlevel 1 (
  echo.
  echo   [!] ดึงโค้ดไม่สำเร็จ
  echo       ถ้าขึ้นว่ามีไฟล์แก้ค้างอยู่ ให้เก็บก่อนด้วย:  git stash
  echo       แล้วเปิด update.bat อีกครั้ง
  echo.
  pause
  exit /b 1
)

echo.
echo อัปเดตเรียบร้อย — กำลังเปิดแอป ...
echo.
call start.bat
