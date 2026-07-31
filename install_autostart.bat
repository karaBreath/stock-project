@echo off
REM NEBULA / Trade World News - make it start by itself at every logon.
REM
REM After this, there is nothing left to open: the app is simply always
REM running, and the desktop icon just shows the page. Same arrangement as
REM volume-edge, which is the one that actually gets used.
REM
REM /RL LIMITED on purpose: this needs no admin rights, so the task can be
REM created from a normal double-click instead of failing on a UAC prompt.
REM
REM ASCII only on purpose - Thai text inside a .bat breaks cmd.
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Trade World News - autostart

echo.
echo   Trade World News - start automatically at logon
echo   ----------------------------------------------
echo.

schtasks /Create /TN "TradeWorldNews" ^
  /TR "wscript.exe \"%~dp0run-hidden.vbs\"" ^
  /SC ONLOGON /RL LIMITED /F

if errorlevel 1 (
  echo.
  echo   [!] Could not create the task.
  echo       Right-click this file and pick "Run as administrator", then retry.
  echo.
  pause
  exit /b 1
)

echo.
echo   Done. It will start on its own from the next logon.
echo   Starting it now as well, so there is nothing to wait for.

start "" wscript.exe "%~dp0run-hidden.vbs"

echo.
echo   Open  http://127.0.0.1:5000  in about a minute.
echo   To turn this off later: uninstall_autostart.bat
echo.
pause
endlocal
