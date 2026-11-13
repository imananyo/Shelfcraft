<#
.SYNOPSIS
  Start Shelfcraft (backend API + web app) and open it in your browser.
.PARAMETER Prod
  Build and run the optimized production web app (faster UI; first build takes ~1–2 min).
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\start.ps1
  powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -Prod
#>
param([switch]$Prod, [int]$ApiPort = 8000, [int]$WebPort = 3000, [switch]$NoBrowser)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
$py = Join-Path $Root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "Backend not set up. Run scripts\setup.ps1 first." }
if (-not (Test-Path (Join-Path $Root "frontend\node_modules"))) { throw "Frontend not set up. Run scripts\setup.ps1 first." }

function Port-Busy($p) { [bool](Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue) }
if (Port-Busy $ApiPort) { throw "Port $ApiPort is already in use (is Shelfcraft already running? run scripts\stop.ps1)" }
if (Port-Busy $WebPort) { throw "Port $WebPort is already in use (run scripts\stop.ps1 or pass -WebPort)" }

# Ollama: start the local server if installed and not running (optional).
if (Get-Command ollama -ErrorAction SilentlyContinue) {
  try { Invoke-RestMethod http://127.0.0.1:11434/api/version -TimeoutSec 2 | Out-Null }
  catch { Start-Process ollama -ArgumentList 'serve' -WindowStyle Hidden; Write-Host "Started Ollama (local AI)." }
}

$logs = Join-Path $Root "data\logs"; New-Item -ItemType Directory -Force $logs | Out-Null
Write-Host "Starting API on http://127.0.0.1:$ApiPort ..." -ForegroundColor Cyan
$api = Start-Process $py -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port","$ApiPort","--timeout-graceful-shutdown","15" `
  -WorkingDirectory (Join-Path $Root "backend") -WindowStyle Minimized -PassThru `
  -RedirectStandardOutput "$logs\api-stdout.log" -RedirectStandardError "$logs\api-stderr.log"

$web = Join-Path $Root "frontend"
$env:SHELFCRAFT_API_ORIGIN = "http://127.0.0.1:$ApiPort"
if ($Prod) {
  Write-Host "Building web app (production)..." -ForegroundColor Cyan
  Push-Location $web; npm run build; if ($LASTEXITCODE -ne 0) { Pop-Location; Stop-Process $api.Id; throw "Build failed" }; Pop-Location
  $webProc = Start-Process "cmd.exe" -ArgumentList "/c","npm run start -- -p $WebPort -H 127.0.0.1 > `"$logs\web.log`" 2>&1" -WorkingDirectory $web -WindowStyle Minimized -PassThru
} else {
  $webProc = Start-Process "cmd.exe" -ArgumentList "/c","npm run dev -- -p $WebPort -H 127.0.0.1 > `"$logs\web.log`" 2>&1" -WorkingDirectory $web -WindowStyle Minimized -PassThru
}
@{ api = $api.Id; web = $webProc.Id } | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $Root "data\.pids.json")

Write-Host "Waiting for services..."
$ok = $false
for ($i = 0; $i -lt 90; $i++) {
  Start-Sleep 2
  try { $h = Invoke-RestMethod "http://127.0.0.1:$ApiPort/api/health" -TimeoutSec 3; Invoke-WebRequest "http://127.0.0.1:$WebPort" -UseBasicParsing -TimeoutSec 5 | Out-Null; $ok = $true; break } catch {}
}
if (-not $ok) { Write-Warning "Services didn't respond in time. Check data\logs\api-stderr.log and data\logs\web.log"; exit 1 }
Write-Host "Shelfcraft is running: http://127.0.0.1:$WebPort   (API health: $($h.status))" -ForegroundColor Green
Write-Host "Stop it with: powershell -ExecutionPolicy Bypass -File scripts\stop.ps1"
if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$WebPort" }
