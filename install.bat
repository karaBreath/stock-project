@echo off
REM NEBULA / Trade World News - one-click installer.
REM
REM Double-click this file. Nothing to type, nothing to paste.
REM
REM Why this downloads to a file first instead of piping the script straight
REM into PowerShell: "irm <url> | iex" runs a script that never touches disk,
REM which is exactly the shape of a malware download cradle. Antivirus and
REM Defender heuristics block that pattern on sight, and the block surfaces as
REM a plain error with no hint that AV was involved at all. Saving the file and
REM running it as a file looks like what it is, and goes through.
REM
REM ASCII only on purpose - the legacy console font has no Thai glyphs, so
REM Thai text here would render as empty boxes and look like a crash.
setlocal
title NEBULA setup

echo.
echo   NEBULA / Trade World News  -  setup
echo   ----------------------------------
echo.
echo   Downloading the installer...
echo.

set "URL=https://raw.githubusercontent.com/karaBreath/stock-project/main/setup.ps1"
set "PS1=%TEMP%\nebula-setup.ps1"
set "LOG=%USERPROFILE%\nebula-log.txt"

powershell -NoProfile -ExecutionPolicy Bypass -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch {}; try { Invoke-WebRequest -Uri $env:URL -OutFile $env:PS1 -UseBasicParsing } catch { Write-Host ''; Write-Host ('  [X] Could not download the installer: ' + $_.Exception.Message) -ForegroundColor Red; exit 1 }"

if errorlevel 1 (
  echo.
  echo   Check your internet connection, then try again.
  echo.
  pause
  exit /b 1
)

REM A file downloaded from the internet carries a "mark of the web" tag.
REM Without clearing it, PowerShell can refuse to run the file with a warning
REM that reads like a virus alert.
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Unblock-File -Path $env:PS1 } catch {}"

echo   Running the installer...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"

if errorlevel 1 (
  echo.
  echo   [!] Setup did not finish.
  echo       A log was saved to: %LOG%
  echo       Send that file and the problem can be read off it directly.
  echo.
)

pause
endlocal
