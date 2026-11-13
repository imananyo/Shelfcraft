<#
.SYNOPSIS
  One-time setup for Shelfcraft on Windows: Python 3.12 venv, backend deps, frontend deps, .env.
.DESCRIPTION
  Safe to re-run. Does not install system software unless -InstallPrereqs is passed
  (then uses winget for Python 3.12, Node LTS, FFmpeg, Ollama, VC++ runtime — all free).
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -InstallPrereqs -WithLocalImageModel
#>
param(
  [switch]$InstallPrereqs,
  [switch]$WithLocalImageModel,
  [switch]$PullOllamaModels
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
function Refresh-Path { $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User') }
function Step($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }
function Have($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

if ($InstallPrereqs) {
  Step "Installing prerequisites with winget (free software; you may see UAC prompts)"
  foreach ($id in 'Python.Python.3.12','OpenJS.NodeJS.LTS','Gyan.FFmpeg','Ollama.Ollama','Microsoft.VCRedist.2015+.x64') {
    winget install --id $id -e --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
  }
  Refresh-Path
}

Step "Checking prerequisites"
Refresh-Path
$py312 = $null
try { $py312 = (& py -3.12 -c "import sys;print(sys.executable)" 2>$null) } catch {}
if (-not $py312) { throw "Python 3.12 not found. Install it (winget install Python.Python.3.12) or re-run with -InstallPrereqs." }
if (-not (Have node)) { throw "Node.js not found. Install Node 20+ (winget install OpenJS.NodeJS.LTS) or re-run with -InstallPrereqs." }
Write-Host "Python 3.12: $py312"
Write-Host "Node: $(node --version)"
if (Have ffmpeg) { Write-Host "FFmpeg: found" } else { Write-Warning "FFmpeg not on PATH — video export will be unavailable until it is installed." }
if (Have ollama) { Write-Host "Ollama: found" } else { Write-Warning "Ollama not found — local text AI unavailable (hosted free tiers can still be configured)." }

Step "Backend: virtual environment + dependencies"
$venv = Join-Path $Root "backend\.venv"
if (-not (Test-Path "$venv\Scripts\python.exe")) { & py -3.12 -m venv $venv }
& "$venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
& "$venv\Scripts\python.exe" -m pip install -r (Join-Path $Root "backend\requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
# OCR engine for "image → layers" (no-deps: keeps opencv-python-headless instead of pulling opencv-python)
& "$venv\Scripts\python.exe" -m pip install --quiet --no-deps rapidocr-onnxruntime

# onnxruntime needs the Microsoft VC++ runtime. If it isn't installed system-wide, place the DLLs
# from the 'msvc-runtime' wheel next to the native modules (no admin rights needed).
& "$venv\Scripts\python.exe" -c "import onnxruntime" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Warning "onnxruntime could not load (missing VC++ runtime). Applying no-admin fallback."
  & "$venv\Scripts\python.exe" -m pip install --quiet msvc-runtime
  $dlls = Get-ChildItem "$venv\Scripts" -Include msvcp140*.dll,vcruntime140*.dll,concrt140.dll -Recurse
  foreach ($target in @("$venv\Lib\site-packages\onnxruntime\capi", "$venv\Lib\site-packages\torch\lib")) {
    if (Test-Path $target) { $dlls | ForEach-Object { Copy-Item $_.FullName $target -Force } }
  }
  & "$venv\Scripts\python.exe" -c "import onnxruntime; print('onnxruntime OK')"
}

Step "Backend: environment file"
$envFile = Join-Path $Root "backend\.env"
if (-not (Test-Path $envFile)) { Copy-Item (Join-Path $Root "backend\.env.example") $envFile; Write-Host "Created backend\.env (all providers optional)." }

Step "Frontend: npm install"
Push-Location (Join-Path $Root "frontend")
npm install --no-fund --no-audit
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "npm install failed" }
Pop-Location

if ($WithLocalImageModel) { & (Join-Path $PSScriptRoot "install-local-image-model.ps1") }
if ($PullOllamaModels -and (Have ollama)) {
  Step "Pulling local Ollama models (qwen2.5:3b ~1.9 GB, nomic-embed-text ~270 MB)"
  ollama pull qwen2.5:3b
  ollama pull nomic-embed-text
}

Write-Host "`nSetup complete. Start Shelfcraft with:  powershell -ExecutionPolicy Bypass -File scripts\start.ps1" -ForegroundColor Green
