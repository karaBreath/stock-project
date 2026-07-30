@echo off
REM NEBULA updater: pull latest code, then start the app. ASCII only on purpose.
setlocal
cd /d "%~dp0"
title NEBULA - Update

set "BRANCH=claude/stock-trading-project-zjrrcz"

where git >nul 2>nul
if errorlevel 1 (
  echo.
  echo   [!] git not found. Install from https://git-scm.com/download/win
  echo.
  pause
  exit /b 1
)

echo Pulling latest code from %BRANCH% ...
git pull origin %BRANCH%
if errorlevel 1 (
  echo.
  echo   [!] git pull failed.
  echo       If it says you have local changes, run:  git stash
  echo       then run update.bat again.
  echo.
  pause
  exit /b 1
)

echo.
echo Update done. Starting the app ...
echo.
call "%~dp0start.bat"
endlocal
