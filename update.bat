@echo off
REM NEBULA updater: get the latest code, then start the app. ASCII only on purpose.
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

echo Fetching %BRANCH% ...
git fetch origin %BRANCH%
if errorlevel 1 (
  echo.
  echo   [!] Could not reach GitHub. Check your internet connection.
  echo.
  pause
  exit /b 1
)

REM Stand ON the branch before pulling. Pulling a branch while sitting on a
REM different one merges them together and leaves a mess that is hard to undo.
git rev-parse --abbrev-ref HEAD > "%TEMP%\nebula_branch.txt"
set /p CURRENT=<"%TEMP%\nebula_branch.txt"
del "%TEMP%\nebula_branch.txt" >nul 2>nul

if not "%CURRENT%"=="%BRANCH%" (
  echo Switching from %CURRENT% to %BRANCH% ...
  git checkout %BRANCH%
  if errorlevel 1 (
    echo.
    echo   [!] Could not switch branch - you probably edited some files.
    echo       To set your edits aside, run:   git stash
    echo       Then run update.bat again.
    echo.
    pause
    exit /b 1
  )
)

echo Pulling latest code ...
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
echo Latest changes:
git --no-pager log --oneline -3
echo.
echo Update done. Starting the app ...
echo.
call "%~dp0start.bat"
endlocal
