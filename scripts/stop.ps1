<#
.SYNOPSIS
  Gracefully stop Shelfcraft started by scripts\start.ps1. Running jobs are re-queued on next start.
.DESCRIPTION
  Stops the recorded process trees, then stops any process still listening on the Shelfcraft ports
  whose command line identifies it as Shelfcraft's API (uvicorn app.main:app) or web app (Next.js in
  this folder). Unrelated programs are never touched.
#>
param([int]$ApiPort = 8000, [int]$WebPort = 3000)
$Root = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $Root "data\.pids.json"
if (Test-Path $pidFile) {
  $pids = Get-Content $pidFile | ConvertFrom-Json
  foreach ($p in @($pids.web, $pids.api)) { if ($p) { & taskkill /PID $p /T 2>$null | Out-Null } }
  Remove-Item $pidFile -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 2
$stopped = 0
foreach ($port in @($ApiPort, $WebPort)) {
  $owners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
  foreach ($owner in $owners) {
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$owner" -ErrorAction SilentlyContinue
    if (-not $proc) { continue }
    $cmd = [string]$proc.CommandLine
    $isApi = $cmd -match 'uvicorn\s+app\.main:app'
    $isWeb = ($cmd -match 'next') -and ($cmd -like "*$Root*" -or $proc.ExecutablePath -like '*node*')
    if ($isApi -or $isWeb) {
      Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue
      $stopped++
    } else {
      Write-Warning "Port $port is used by another program (PID $owner): left running."
    }
  }
}
Write-Host "Shelfcraft stopped$(if ($stopped) { " ($stopped leftover process(es) cleaned up)" }). Interrupted jobs will resume automatically on next start."
