<#
.SYNOPSIS
  Restore a Shelfcraft backup ZIP. Stop Shelfcraft first (scripts\stop.ps1).
.DESCRIPTION
  Before restoring, the current database and media are moved to data\pre-restore-<timestamp>
  so nothing is lost if you restore the wrong file.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\restore.ps1 -Backup data\backups\shelfcraft-backup-20261113-120000.zip
#>
param([Parameter(Mandatory = $true)][string]$Backup)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$data = Join-Path $Root "data"
if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { throw "Shelfcraft appears to be running. Stop it first with scripts\stop.ps1." }
$Backup = (Resolve-Path $Backup).Path
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [IO.Compression.ZipFile]::OpenRead($Backup)
$hasDb = $zip.Entries | Where-Object { $_.FullName -eq "shelfcraft.db" }
$bad = $zip.Entries | Where-Object { $_.FullName -match '(^|[\\/])\.\.([\\/]|$)' -or $_.FullName -match '^[A-Za-z]:' -or $_.FullName.StartsWith('/') }
$zip.Dispose()
if (-not $hasDb) { throw "Not a Shelfcraft backup (shelfcraft.db missing)." }
if ($bad) { throw "Backup contains unsafe paths; refusing to extract." }

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$safety = Join-Path $data "pre-restore-$stamp"
New-Item -ItemType Directory -Force $safety | Out-Null
foreach ($item in @("shelfcraft.db", "shelfcraft.db-wal", "shelfcraft.db-shm", "media")) {
  $p = Join-Path $data $item
  if (Test-Path $p) { Move-Item $p $safety }
}
Expand-Archive -Path $Backup -DestinationPath $data -Force
Write-Host "Restored from $Backup" -ForegroundColor Green
Write-Host "Previous data kept in $safety (delete it once you've checked the restore)."
