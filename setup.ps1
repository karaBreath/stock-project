# NEBULA one-line installer / launcher
#
# Paste this into the Windows Run box (Win + R):
#   powershell -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/karaBreath/stock-project/main/setup.ps1 | iex"
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

function Say([string]$m) { Write-Host "  $m" }
function Die([string]$m) {
  Write-Host ""
  Write-Host "  [X] $m" -ForegroundColor Red
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
  # Store instead of running anything, so check the usual real install paths.
  foreach ($p in @(
      "$home_\AppData\Local\Programs\Python\Python313\python.exe",
      "$home_\AppData\Local\Programs\Python\Python312\python.exe",
      "$home_\AppData\Local\Programs\Python\Python311\python.exe",
      "$home_\AppData\Local\Programs\Python\Python310\python.exe",
      "C:\Python313\python.exe", "C:\Python312\python.exe",
      "C:\Python311\python.exe", "C:\Python310\python.exe")) {
    if (Test-Path $p) { return $p }
  }
  return $null
}

$py = Find-Python
if (-not $py) {
  Write-Host ""
  Write-Host "  [X] Python is not installed on this PC." -ForegroundColor Red
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
# 5) desktop icon + open the window
# --------------------------------------------------------------------------
Say "Creating the desktop icon..."
try {
  & $pyExe @pyArgs (Join-Path $root 'services\desktop.py')
} catch {
  Say "Could not create the icon (not fatal): $($_.Exception.Message)"
}

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
