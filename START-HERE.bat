@echo off
REM ===========================================================================
REM Trade World News - double-click this file. That is the whole procedure.
REM
REM This is the route that does not download anything at the moment it runs.
REM The code is already here, next to this file, because the browser fetched
REM the whole folder as a zip. Every other route so far has failed at the same
REM place: PowerShell reaching out to the network while an antivirus, a proxy
REM or a TLS setting quietly refuses. Nothing to refuse here.
REM
REM The one thing it still fetches is Python itself, and only when the PC does
REM not have it - through winget, which is a Windows component and is not
REM treated as a download cradle.
REM
REM ASCII only on purpose: the legacy console font has no Thai glyphs, and Thai
REM text inside a .bat can make cmd.exe lose its place in the file and exit
REM without a word. Thai belongs in the app window, not here.
REM ===========================================================================
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set "LOG=%USERPROFILE%\nebula-log.txt"
title Trade World News

> "%LOG%" echo === START-HERE %DATE% %TIME% ===

echo.
echo   Trade World News
echo   ----------------
echo.

REM ---------------------------------------------------------------------------
REM 1) find Python
REM ---------------------------------------------------------------------------
set "PY="
if exist "%~dp0venv\Scripts\python.exe" set "PY=%~dp0venv\Scripts\python.exe"
if not defined PY py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY python --version >nul 2>nul && set "PY=python"

if not defined PY (
  echo   Python is not installed on this PC.
  echo   Installing it now - takes 2 to 4 minutes, nothing to click.
  echo   Please leave this window open.
  echo.
  winget install --id Python.Python.3.12 --source winget --scope user --accept-package-agreements --accept-source-agreements --silent >> "%LOG%" 2>&1

  REM winget updates PATH only for processes started after it, so this window
  REM still cannot see Python. Look on disk instead of asking for a restart.
  for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%D\python.exe" set "PY=%%D\python.exe"
  )
  if defined PY echo   Python installed.
)

if not defined PY (
  echo.
  echo   [X] Could not install Python automatically.
  echo       Opening the download page now.
  echo       IMPORTANT: tick "Add python.exe to PATH" during setup,
  echo       then double-click this file again.
  echo.
  >> "%LOG%" echo   PYTHON-MISSING
  start "" https://www.python.org/downloads/
  pause
  exit /b 1
)

echo   Python: %PY%
>> "%LOG%" echo   Python: %PY%

REM ---------------------------------------------------------------------------
REM 2) desktop icon - not fatal if it fails, so never stop on it
REM ---------------------------------------------------------------------------
echo   Creating the desktop icon...
%PY% "%~dp0services\desktop.py" >> "%LOG%" 2>&1

REM ---------------------------------------------------------------------------
REM 3) start by itself at every logon, hidden
REM ---------------------------------------------------------------------------
echo   Setting it to start by itself at logon...
schtasks /Create /TN "TradeWorldNews" /TR "wscript.exe \"%~dp0run-hidden.vbs\"" /SC ONLOGON /RL LIMITED /F >> "%LOG%" 2>&1

REM ---------------------------------------------------------------------------
REM 4) run it
REM ---------------------------------------------------------------------------
echo.
echo   Starting. The first run takes 2-5 minutes while the libraries
echo   install. The browser opens by itself when it is ready.
echo.

%PY% "%~dp0launcher.py"
set "RC=%ERRORLEVEL%"
>> "%LOG%" echo   launcher exit code %RC%

if not "%RC%"=="0" (
  echo.
  echo   [X] It stopped with code %RC%.
  echo.
  echo       A full log is at:  %LOG%
  echo       Send that file, or just the last red line above.
  echo.
  pause
)

endlocal
