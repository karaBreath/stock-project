@echo off
REM NEBULA / Trade World News - entry point used by the logon task.
REM
REM Never call pause in here. Nobody can see this window (it is launched
REM hidden by run-hidden.vbs), so a pause would wait forever on a prompt
REM that does not exist, and the app would simply never come up.
REM
REM --no-browser on purpose: this runs at every logon, and a browser tab
REM opening by itself on every boot is not a feature anyone asked for.
REM The desktop icon opens the page when the user actually wants it.
REM
REM ASCII only on purpose - Thai text inside a .bat breaks cmd.
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1

REM Prefer the venv: it already has the libraries, so startup is instant
REM instead of re-resolving them through the system interpreter.
if exist "%~dp0venv\Scripts\pythonw.exe" (
  "%~dp0venv\Scripts\pythonw.exe" "%~dp0launcher.py" --no-browser
  exit /b %ERRORLEVEL%
)

set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY python --version >nul 2>nul && set "PY=python"
if not defined PY exit /b 1

%PY% "%~dp0launcher.py" --no-browser
endlocal
