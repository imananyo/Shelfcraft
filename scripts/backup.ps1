<#
.SYNOPSIS
  Create a backup ZIP (database + media). Works whether or not Shelfcraft is running.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\backup.ps1 -Destination D:\Backups
#>
param([string]$Destination)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $Root "backend\.venv\Scripts\python.exe"
$code = @'
import sqlite3, sys, zipfile, datetime, pathlib
root = pathlib.Path(sys.argv[1]); dest = pathlib.Path(sys.argv[2]); dest.mkdir(parents=True, exist_ok=True)
data = root / "data"; stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
tmp = dest / f"db-{stamp}.sqlite"
src = sqlite3.connect(data / "shelfcraft.db"); dst = sqlite3.connect(tmp)
with dst: src.backup(dst)   # consistent online snapshot even while the app runs
src.close(); dst.close()
out = dest / f"shelfcraft-backup-{stamp}.zip"
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    z.write(tmp, "shelfcraft.db")
    media = data / "media"
    for f in media.rglob("*"):
        if f.is_file() and f.relative_to(media).parts[0] != "tmp":
            z.write(f, "media/" + f.relative_to(media).as_posix())
tmp.unlink()
print(out)
'@
if (-not $Destination) { $Destination = Join-Path $Root "data\backups" }
$out = & $py -c $code $Root $Destination
Write-Host "Backup written: $out" -ForegroundColor Green
