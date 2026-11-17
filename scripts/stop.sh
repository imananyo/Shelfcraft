#!/usr/bin/env bash
# Gracefully stop Shelfcraft started by ./scripts/start.sh. Running jobs are re-queued on next start.
# Stops the recorded process trees, then any process still listening on the Shelfcraft ports whose
# command line identifies it as Shelfcraft's API (uvicorn app.main:app) or web app (Next.js).
# Unrelated programs are never touched.
#   ./scripts/stop.sh [--api-port 8000] [--web-port 3000]
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_PORT=8000; WEB_PORT=3000
while [ $# -gt 0 ]; do
  case "$1" in
    --api-port) API_PORT="$2"; shift ;;
    --web-port) WEB_PORT="$2"; shift ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

kill_tree() {  # terminate a process and all of its descendants
  local pid="$1" child
  for child in $(pgrep -P "$pid" 2>/dev/null); do kill_tree "$child"; done
  kill -TERM "$pid" 2>/dev/null || true
}

PIDS="$ROOT/data/.pids.json"
if [ -f "$PIDS" ]; then
  for p in $(grep -oE '[0-9]+' "$PIDS"); do kill_tree "$p"; done
  rm -f "$PIDS"
fi
sleep 2

STOPPED=0
if command -v lsof >/dev/null 2>&1; then
  for port in "$API_PORT" "$WEB_PORT"; do
    for owner in $(lsof -t -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u); do
      cmd="$(ps -o command= -p "$owner" 2>/dev/null || true)"
      if printf '%s' "$cmd" | grep -Eq 'uvicorn +app\.main:app|next'; then
        kill -TERM "$owner" 2>/dev/null && STOPPED=$((STOPPED + 1))
      else
        echo "WARNING: port $port is used by another program (PID $owner): left running." >&2
      fi
    done
  done
fi
msg="Shelfcraft stopped"
[ "$STOPPED" -gt 0 ] && msg="$msg ($STOPPED leftover process(es) cleaned up)"
echo "$msg. Interrupted jobs will resume automatically on next start."
