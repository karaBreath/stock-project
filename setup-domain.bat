@echo off
REM NEBULA: one-click setup for your own domain. ASCII only on purpose.
setlocal
cd /d "%~dp0"
title NEBULA - Setup your own domain

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

echo.
echo   ==================================================================
echo     Set up your own fixed web address
echo   ------------------------------------------------------------------
echo     Example:  nebula.twinpatta.com
echo.
echo     You need a free Cloudflare account, and your main domain
echo     must already be added to that Cloudflare account.
echo   ==================================================================
echo.

set "DOMAIN="
set /p "DOMAIN=Type the address you want (or press Enter for nebula.twinpatta.com): "
if "%DOMAIN%"=="" set "DOMAIN=nebula.twinpatta.com"

echo.
echo   Using: %DOMAIN%
echo.

%PY% "%~dp0share.py" --setup-domain %DOMAIN%
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
  echo   Done. From now on just double-click share.bat
) else (
  echo   [!] Setup did not finish. Screenshot this window if you need help.
)
echo.
pause
endlocal
