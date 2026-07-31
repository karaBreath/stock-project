@echo off
REM NEBULA / Trade World News - one-click installer.
REM
REM Double-click this file. Nothing to type, nothing to paste.
REM
REM This exists because the Run-box one-liner has three ways to fail silently:
REM a curly quote pasted from a chat app, TLS 1.2 not being on by default in
REM Windows PowerShell 5.1, and the window closing before any error is
REM readable. A .bat that pauses at the end has none of those problems.
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

REM One physical line on purpose: a trailing space after a ^ continuation is
REM invisible and silently breaks the command.
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch {}; try { $s = (New-Object Net.WebClient).DownloadString($env:URL) } catch { Write-Host ''; Write-Host ('  [X] Could not download the installer: ' + $_.Exception.Message) -ForegroundColor Red; Write-Host '      Check your internet connection, then try again.' -ForegroundColor Yellow; exit 1 }; Invoke-Expression $s"

if errorlevel 1 (
  echo.
  echo   [!] Setup did not finish.
  echo       Screenshot this window if you need help.
  echo.
)

pause
endlocal
