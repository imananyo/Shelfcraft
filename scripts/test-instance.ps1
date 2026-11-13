<#
.SYNOPSIS
  Start or stop an isolated Shelfcraft test instance (API :8100, web :3100) with its own empty database.
.DESCRIPTION
  Your real workspace (data\) is never touched: the test instance uses a separate data folder whose models\
  folder is a junction to data\models (no 5 GB copy). Use it for E2E runs and the real-model feature sweep:
    scripts\test-instance.ps1                 # start (builds the test web app into frontend\.next-test)
    $env:BASE="http://127.0.0.1:3100"; cd frontend; npx playwright test
    backend\.venv\Scripts\python.exe backend\scripts\feature_sweep.py --api http://127.0.0.1:8100
    scripts\test-instance.ps1 -Stop           # stop (add -Wipe to delete the test data)
#>
param([switch]$Stop, [switch]$Wipe, [switch]$NoBuild, [string]$DataDir = "$env:TEMP\shelfcraft-test")
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')

function Stop-Port($port) {
  foreach ($c in Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
    $p = Get-CimInstance Win32_Process -Filter "ProcessId=$($c.OwningProcess)"
    if ($p.CommandLine -match 'uvicorn|next') { Stop-Process -Id $p.ProcessId -Force; Write-Host "stopped :$port (pid $($p.ProcessId))" }
  }
}

if ($Stop) {
  Stop-Port 8100; Stop-Port 3100
  if ($Wipe -and (Test-Path $DataDir)) { cmd /c rmdir /s /q "$DataDir"; Write-Host "deleted $DataDir" }
  return
}

if (-not (Test-Path $DataDir)) { New-Item -ItemType Directory $DataDir | Out-Null }
if (-not (Test-Path "$DataDir\models")) { cmd /c mklink /J "$DataDir\models" "$Root\data\models" | Out-Null }

$env:SHELFCRAFT_DATA_DIR = $DataDir
Start-Process "$Root\backend\.venv\Scripts\python.exe" -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8100" `
  -WorkingDirectory "$Root\backend" -WindowStyle Hidden -RedirectStandardOutput "$DataDir\api-out.log" -RedirectStandardError "$DataDir\api-err.log"
Remove-Item Env:SHELFCRAFT_DATA_DIR

# Next.js bakes the /api rewrite target in at build time, so the test web app has its own build folder.
$env:SHELFCRAFT_DIST_DIR = ".next-test"; $env:SHELFCRAFT_API_ORIGIN = "http://127.0.0.1:8100"
Push-Location "$Root\frontend"
try {
  if (-not $NoBuild -or -not (Test-Path ".next-test\BUILD_ID")) { npm run build; if ($LASTEXITCODE -ne 0) { throw "test build failed" } }
  Start-Process cmd.exe -ArgumentList "/c","npm run start -- -p 3100 -H 127.0.0.1 > `"$DataDir\web.log`" 2>&1" -WindowStyle Hidden
} finally { Pop-Location; Remove-Item Env:SHELFCRAFT_DIST_DIR; Remove-Item Env:SHELFCRAFT_API_ORIGIN }

for ($i = 0; $i -lt 60; $i++) { Start-Sleep 2; try { $s = Invoke-RestMethod http://127.0.0.1:3100/api/auth/status -TimeoutSec 3; break } catch {} }
if ($null -eq $s) { throw "test instance didn't start (see $DataDir\*.log)" }
if ($s.team_mode) { throw "test web app is talking to a backend with team mode on — expected the isolated :8100 backend" }
if (-not (Invoke-RestMethod http://127.0.0.1:8100/api/products).items) {
  & "$Root\backend\.venv\Scripts\python.exe" "$Root\backend\scripts\seed_demo.py" --api http://127.0.0.1:8100 | Out-Null
}
Write-Host "Test instance ready: http://127.0.0.1:3100 (API :8100, data $DataDir)" -ForegroundColor Green
