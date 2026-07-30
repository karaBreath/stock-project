@echo off
REM NEBULA: open the app to the internet through Cloudflare Tunnel. ASCII only.
setlocal
cd /d "%~dp0"
title NEBULA - Share online

set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY python --version >nul 2>nul && set "PY=python"
if not defined PY python3 --version >nul 2>nul && set "PY=python3"

if not defined PY (
  echo.
  echo   [!] Python not found. Run start.bat first.
  echo.
  pause
  exit /b 1
)

%PY% "%~dp0share.py" %*
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
  echo.
  echo   [!] Exited with code %RC%
  echo.
  pause
)
endlocal
