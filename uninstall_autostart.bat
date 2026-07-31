@echo off
REM NEBULA / Trade World News - stop starting at logon.
REM ASCII only on purpose - Thai text inside a .bat breaks cmd.
setlocal
chcp 65001 >nul
title Trade World News - remove autostart

echo.
schtasks /Delete /TN "TradeWorldNews" /F
echo.
echo   Autostart removed. The app no longer starts by itself.
echo   You can still open it from the desktop icon any time.
echo.
pause
endlocal
