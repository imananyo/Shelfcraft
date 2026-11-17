#!/usr/bin/env bash
# Restore a Shelfcraft backup ZIP on macOS/Linux. Stop Shelfcraft first (./scripts/stop.sh).
# The current database and media are moved to data/pre-restore-<timestamp> first, so nothing is
# lost if you restore the wrong file.
#   ./scripts/restore.sh data/backups/shelfcraft-backup-20261113-120000.zip
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA="$ROOT/data"
PY="$ROOT/backend/.venv/bin/python"
[ $# -eq 1 ] || { echo "Usage: $0 <backup.zip>" >&2; exit 2; }
BACKUP="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
[ -f "$BACKUP" ] || { echo "Backup not found: $1" >&2; exit 1; }
[ -x "$PY" ] || { echo "Run ./scripts/setup.sh first." >&2; exit 1; }
if curl -fsS --max-time 2 http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
  echo "Shelfcraft appears to be running. Stop it first with ./scripts/stop.sh." >&2; exit 1
fi

# Validate (must contain shelfcraft.db, no absolute or ../ paths) before touching anything.
"$PY" - "$BACKUP" <<'EOF'
import re, sys, zipfile
names = zipfile.ZipFile(sys.argv[1]).namelist()
if "shelfcraft.db" not in names:
    sys.exit("Not a Shelfcraft backup (shelfcraft.db missing).")
if any(n.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", n) or re.search(r"(^|[\\/])\.\.([\\/]|$)", n) for n in names):
    sys.exit("Backup contains unsafe paths; refusing to extract.")
EOF

SAFETY="$DATA/pre-restore-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$SAFETY"
for item in shelfcraft.db shelfcraft.db-wal shelfcraft.db-shm media; do
  [ -e "$DATA/$item" ] && mv "$DATA/$item" "$SAFETY/"
done
"$PY" -c "import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" "$BACKUP" "$DATA"
echo "Restored from $BACKUP"
echo "Previous data kept in $SAFETY (delete it once you've checked the restore)."
