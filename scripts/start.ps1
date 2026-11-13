<#
.SYNOPSIS
  Start Shelfcraft (backend API + web app) and open it in your browser.
.PARAMETER Prod
  Build and run the optimized production web app (faster UI; first build takes ~1–2 min).
.PARAMETER Lan
  Let other devices on your network use Shelfcraft (for team members). Only allowed when team mode is
  enabled (Settings → Team), so every request requires a sign-in or an API key.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\start.ps1
  powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -Prod
  powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -Prod -Lan
#>
param([switch]$Prod, [int]$ApiPort = 8000, [int]$WebPort = 3000, [switch]$NoBrowser, [switch]$Lan)
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
$webHost = "127.0.0.1"
if ($Lan) {
  # The API itself always stays on 127.0.0.1; only the web app (which proxies /api and /v1) is opened to the LAN,
  # and only when team mode guarantees every request is authenticated.
  $ready = $false
  for ($i = 0; $i -lt 60; $i++) { Start-Sleep 1; try { $st = Invoke-RestMethod "http://127.0.0.1:$ApiPort/api/auth/status" -TimeoutSec 3; $ready = $true; break } catch {} }
  if ($ready -and $st.team_mode) { $webHost = "0.0.0.0"; Write-Host "LAN access enabled (team mode is on)." -ForegroundColor Yellow }
  else { Write-Warning "LAN access refused: enable team mode first (Settings → Team). Starting on this computer only." }
}
if ($Prod) {
  Write-Host "Building web app (production)..." -ForegroundColor Cyan
  Push-Location $web; npm run build; if ($LASTEXITCODE -ne 0) { Pop-Location; Stop-Process $api.Id; throw "Build failed" }; Pop-Location
  $webProc = Start-Process "cmd.exe" -ArgumentList "/c","npm run start -- -p $WebPort -H $webHost > `"$logs\web.log`" 2>&1" -WorkingDirectory $web -WindowStyle Minimized -PassThru
} else {
  $webProc = Start-Process "cmd.exe" -ArgumentList "/c","npm run dev -- -p $WebPort -H $webHost > `"$logs\web.log`" 2>&1" -WorkingDirectory $web -WindowStyle Minimized -PassThru
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
if ($webHost -eq "0.0.0.0") {
  # Prefer the adapter that has a default gateway (your real Wi-Fi/Ethernet), not virtual adapters.
  $cfg = Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } | Select-Object -First 1
  $ip = if ($cfg) { $cfg.IPv4Address.IPAddress | Select-Object -First 1 } else {
    (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.PrefixOrigin -ne 'WellKnown' } | Select-Object -First 1).IPAddress }
  Write-Host "Phone app / teammates on your Wi-Fi: http://${ip}:$WebPort  (Windows Firewall may ask to allow Node.js — allow on Private networks only)" -ForegroundColor Yellow
}
Write-Host "Stop it with: powershell -ExecutionPolicy Bypass -File scripts\stop.ps1"
if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$WebPort" }
