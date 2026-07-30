@echo off
REM NEBULA launcher. ASCII only on purpose: Thai text + chcp inside a .bat
REM can make cmd.exe lose its place in the file and exit silently.
setlocal
cd /d "%~dp0"
title NEBULA Stock Analysis

set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY python --version >nul 2>nul && set "PY=python"
if not defined PY python3 --version >nul 2>nul && set "PY=python3"

if not defined PY (
  echo.
  echo   [!] Python not found on this PC.
  echo.
  echo   Install it from https://www.python.org/downloads/
  echo   IMPORTANT: tick "Add python.exe to PATH" during setup,
  echo   then close this window and run start.bat again.
  echo.
  pause
  exit /b 1
)

%PY% "%~dp0launcher.py" %*
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
  echo.
  echo   [!] Launcher exited with code %RC%
  echo       Screenshot this window if you need help.
  echo.
  pause
)
endlocal
