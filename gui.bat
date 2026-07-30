@echo off
REM NEBULA GUI launcher. ASCII only on purpose (Thai text inside .bat breaks cmd).
setlocal
cd /d "%~dp0"

REM Prefer pythonw so no black console window appears next to the app window.
if exist "%~dp0venv\Scripts\pythonw.exe" (
  start "" "%~dp0venv\Scripts\pythonw.exe" "%~dp0gui.py"
  exit /b 0
)

pythonw --version >nul 2>nul
if not errorlevel 1 (
  start "" pythonw "%~dp0gui.py"
  exit /b 0
)

set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY python --version >nul 2>nul && set "PY=python"

if not defined PY (
  echo.
  echo   [!] Python not found.
  echo   Install from https://www.python.org/downloads/
  echo   IMPORTANT: tick "Add python.exe to PATH" during setup.
  echo.
  pause
  exit /b 1
)

%PY% "%~dp0gui.py"
endlocal
