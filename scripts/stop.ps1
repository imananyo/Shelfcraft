<#
.SYNOPSIS
  Gracefully stop Shelfcraft started by scripts\start.ps1. Running jobs are re-queued on next start.
#>
$Root = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $Root "data\.pids.json"
if (-not (Test-Path $pidFile)) { Write-Host "No running instance recorded."; exit 0 }
$pids = Get-Content $pidFile | ConvertFrom-Json
foreach ($p in @($pids.web, $pids.api)) {
  if ($p) {
    # taskkill /T ends the process tree (npm → node) without touching unrelated processes.
    & taskkill /PID $p /T 2>$null | Out-Null
  }
}
Remove-Item $pidFile -ErrorAction SilentlyContinue
Write-Host "Shelfcraft stopped. Interrupted jobs will resume automatically on next start."
