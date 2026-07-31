# NEBULA one-line installer / launcher
#
# Paste this into the Windows Run box (Win + R). It deliberately contains no
# double quotes: chat apps and rendered docs turn " into a curly quote, and a
# curly quote makes PowerShell fail to parse the line and close instantly.
#   powershell -nop -exec Bypass -Command try{[Net.ServicePointManager]::SecurityProtocol=3072;iex(irm https://raw.githubusercontent.com/karaBreath/stock-project/main/setup.ps1)}catch{$_;Read-Host}
#
# Or, with nothing to type at all: download install.bat and double-click it.
#
# It finds the project folder wherever it already is, installs it if it is not
# there yet, updates it, puts an icon on the desktop, and opens the app window.
#
# NOTE: every message printed here is ASCII on purpose. The legacy Windows
# console font has no Thai glyphs, so Thai text would show up as empty boxes
# and look like an error. Thai belongs in the app window, not here.

$ErrorActionPreference = 'Stop'
$REPO = 'https://github.com/karaBreath/stock-project.git'
$ZIP  = 'https://codeload.github.com/karaBreath/stock-project/zip/refs/heads/main'

# Windows PowerShell 5.1 still negotiates TLS 1.0 first on many machines, and
# GitHub refuses it. Without this, every download below dies with a bare
# "Could not create SSL/TLS secure channel".
try {
  [Net.ServicePointManager]::SecurityProtocol =
    [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
} catch { }

function Say([string]$m) { Write-Host "  $m" }
function Die([string]$m) {
  Write-Host ""
  Write-Host "  [X] $m" -ForegroundColor Red
  Write-Host ""
  Read-Host "  Press Enter to close"
  exit 1
}

# The window is launched by the Run box, so when this script throws the window
# vanishes with it and the user is left with a flash and no message. Catch
# everything, show it, and hold the window open so there is something to read
# (and to screenshot).
trap {
  Write-Host ""
  Write-Host "  [X] Setup stopped with an unexpected error:" -ForegroundColor Red
  Write-Host "      $($_.Exception.Message)" -ForegroundColor Red
  if ($_.InvocationInfo) {
    Write-Host "      (line $($_.InvocationInfo.ScriptLineNumber))" -ForegroundColor DarkGray
  }
  Write-Host ""
  Write-Host "  Screenshot this window if you need help." -ForegroundColor Yellow
  Write-Host ""
  Read-Host "  Press Enter to close"
  exit 1
}

Write-Host ""
Write-Host "  NEBULA / Trade World News  -  setup" -ForegroundColor Cyan
Write-Host "  ----------------------------------" -ForegroundColor DarkGray

# --------------------------------------------------------------------------
# 1) where is it?
# --------------------------------------------------------------------------
function Is-Project([string]$p) {
  if (-not $p) { return $false }
  return (Test-Path (Join-Path $p 'requirements.txt')) -and
         (Test-Path (Join-Path $p 'launcher.py'))
}

# Ask Windows for the real desktop. Never assume %USERPROFILE%\Desktop --
# with OneDrive turned on the desktop moves, and guessing wrong means the
# icon lands somewhere the user cannot see.
$desktop = [Environment]::GetFolderPath('Desktop')
$home_   = $env:USERPROFILE

$candidates = @(
  (Join-Path $desktop 'stock-project'),
  (Join-Path $home_   'Desktop\stock-project'),
  (Join-Path $home_   'OneDrive\Desktop\stock-project'),
  (Join-Path $home_   'stock-project'),
  (Join-Path $home_   'Documents\stock-project'),
  (Join-Path $home_   'Downloads\stock-project')
)

$root = $null
foreach ($c in $candidates) { if (Is-Project $c) { $root = $c; break } }

if (-not $root) {
  Say "Looking for an existing copy..."
  try {
    $hit = Get-ChildItem -Path $home_ -Directory -Filter 'stock-project' `
             -Recurse -Depth 4 -ErrorAction SilentlyContinue |
           Where-Object { Is-Project $_.FullName } |
           Select-Object -First 1
    if ($hit) { $root = $hit.FullName }
  } catch { }
}

# --------------------------------------------------------------------------
# 2) install it if it is missing
# --------------------------------------------------------------------------
$hasGit = $null -ne (Get-Command git -ErrorAction SilentlyContinue)

if (-not $root) {
  $root = Join-Path $desktop 'stock-project'
  Say "Not installed yet -> installing to:"
  Say "  $root"
  if ($hasGit) {
    git clone --depth 1 $REPO "$root" 2>&1 | Out-Null
  } else {
    # No git on this machine: fall back to the plain zip download so the
    # user is not blocked on installing a second tool first.
    Say "git not found, downloading zip instead..."
    $tmp = Join-Path $env:TEMP 'nebula.zip'
    $out = Join-Path $env:TEMP 'nebula-unzip'
    if (Test-Path $out) { Remove-Item $out -Recurse -Force }
    try {
      [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
      Invoke-WebRequest -Uri $ZIP -OutFile $tmp -UseBasicParsing
      Expand-Archive -Path $tmp -DestinationPath $out -Force
      $inner = Get-ChildItem $out -Directory | Select-Object -First 1
      Move-Item $inner.FullName $root
    } catch {
      Die "Download failed: $($_.Exception.Message)"
    }
  }
  if (-not (Is-Project $root)) { Die "Install did not complete. Check your internet connection." }
  Say "Installed."
} else {
  Say "Found: $root"
}

Set-Location $root

# --------------------------------------------------------------------------
# 3) pull the latest code (never throw away the user's own edits)
# --------------------------------------------------------------------------
if ($hasGit -and (Test-Path (Join-Path $root '.git'))) {
  Say "Updating..."
  git fetch origin main 2>&1 | Out-Null

  git checkout main 2>&1 | Out-Null
  if ($LASTEXITCODE -ne 0) {
    # Local edits block the branch switch. Park them in the stash rather
    # than deleting them -- they are the user's work, not ours to throw away.
    git stash 2>&1 | Out-Null
    git checkout main 2>&1 | Out-Null
    Say "Your local edits were parked in 'git stash'."
  }

  git merge --ff-only origin/main 2>&1 | Out-Null
  if ($LASTEXITCODE -ne 0) {
    git stash 2>&1 | Out-Null
    git merge --ff-only origin/main 2>&1 | Out-Null
    Say "Your local edits were parked in 'git stash'."
  }
}

# --------------------------------------------------------------------------
# 4) find python
# --------------------------------------------------------------------------
function Find-Python {
  $venv = Join-Path $root 'venv\Scripts\python.exe'
  if (Test-Path $venv) { return $venv }
  foreach ($c in @('py', 'python', 'python3')) {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    if ($cmd) {
      $args_ = if ($c -eq 'py') { '-3' } else { $null }
      try {
        if ($args_) { & $cmd.Source $args_ --version *> $null }
        else        { & $cmd.Source --version *> $null }
        if ($LASTEXITCODE -eq 0) { return @($cmd.Source, $args_) }
      } catch { }
    }
  }
  # The Windows Store stub named python.exe exits non-zero and opens the
  # Store instead of running anything, so check the real install paths too.
  # Scan the folder rather than listing versions: a hardcoded list goes stale
  # every October and the failure looks like "Python is not installed" on a
  # machine where it plainly is.
  $progs = Join-Path $home_ 'AppData\Local\Programs\Python'
  $dirs = Get-ChildItem $progs -Directory -ErrorAction SilentlyContinue |
          Sort-Object Name -Descending
  foreach ($d in $dirs) {
    $p = Join-Path $d.FullName 'python.exe'
    if (Test-Path $p) { return $p }
  }
  foreach ($p in @("C:\Python313\python.exe", "C:\Python312\python.exe",
                   "C:\Python311\python.exe", "C:\Python310\python.exe")) {
    if (Test-Path $p) { return $p }
  }
  return $null
}

$py = Find-Python

if (-not $py) {
  # Installing Python by hand is the step people give up on: the download
  # page has several buttons, and the one checkbox that actually matters
  # ("Add python.exe to PATH") is easy to miss -- and missing it means
  # nothing works afterwards, with no hint as to why. winget ships with
  # Windows 10 1809+ and Windows 11, so just do it here.
  Say ""
  Say "Python is not installed yet. Installing it now -- this takes"
  Say "2-4 minutes and needs no clicks. Please leave this window open."
  $winget = Get-Command winget -ErrorAction SilentlyContinue
  if ($winget) {
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'   # winget writes to stderr when it is fine
    try {
      & winget install --id Python.Python.3.12 --source winget --scope user `
          --accept-package-agreements --accept-source-agreements --silent |
        Out-Null
    } catch { }
    $ErrorActionPreference = $old

    # winget only puts Python on the PATH of processes started after it, so
    # this window still cannot see it. Reload PATH instead of asking the user
    # to run the line a second time.
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'User') + ';' +
                [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $py = Find-Python
    if ($py) { Say "Python installed." }
  } else {
    Say "winget is not available on this Windows version."
  }
}

if (-not $py) {
  Write-Host ""
  Write-Host "  [X] Could not install Python automatically." -ForegroundColor Red
  Write-Host "      Opening the download page now." -ForegroundColor Yellow
  Write-Host "      IMPORTANT: tick 'Add python.exe to PATH' during setup," -ForegroundColor Yellow
  Write-Host "      then run this same line again." -ForegroundColor Yellow
  Write-Host ""
  Start-Process 'https://www.python.org/downloads/'
  Read-Host "  Press Enter to close"
  exit 1
}

$pyExe  = if ($py -is [array]) { $py[0] } else { $py }
$pyArgs = if ($py -is [array] -and $py[1]) { @($py[1]) } else { @() }

# --------------------------------------------------------------------------
# 5) desktop icon + start at logon + open the window
# --------------------------------------------------------------------------
Say "Creating the desktop icon..."
try {
  & $pyExe @pyArgs (Join-Path $root 'services\desktop.py')
} catch {
  Say "Could not create the icon (not fatal): $($_.Exception.Message)"
}

# Register the logon task. This is the part that removes opening from the
# routine entirely: the app is simply already running when the user logs in,
# so the icon has nothing to launch -- it just shows the page. Hidden via
# run-hidden.vbs, otherwise every boot would flash a black console window.
#
# /RL LIMITED needs no admin rights, so this works from a plain double-click.
Say "Setting it to start by itself at logon..."
$old = $ErrorActionPreference
$ErrorActionPreference = 'Continue'   # schtasks writes to stderr when it is fine
try {
  $vbs = Join-Path $root 'run-hidden.vbs'
  & schtasks /Create /TN 'TradeWorldNews' /TR "wscript.exe `"$vbs`"" `
      /SC ONLOGON /RL LIMITED /F | Out-Null
  if ($LASTEXITCODE -eq 0) {
    Say "Autostart is on -- from the next logon it is already running."
  } else {
    Say "Could not set up autostart (not fatal). Run install_autostart.bat later."
  }
} catch {
  Say "Could not set up autostart (not fatal): $($_.Exception.Message)"
}
$ErrorActionPreference = $old

Say "Opening the app window..."
$pyw = Join-Path (Split-Path $pyExe) 'pythonw.exe'
$gui = Join-Path $root 'gui.py'
if ((Test-Path $pyw) -and $pyArgs.Count -eq 0) {
  Start-Process -FilePath $pyw -ArgumentList "`"$gui`"" -WorkingDirectory $root
} else {
  Start-Process -FilePath $pyExe -ArgumentList ($pyArgs + "`"$gui`"") -WorkingDirectory $root
}

Write-Host ""
Write-Host "  Done. The app window is opening." -ForegroundColor Green
Write-Host "  Next time: just double-click the desktop icon." -ForegroundColor Green
Write-Host ""
Start-Sleep -Seconds 4
