#!/usr/bin/env bash
# Start Shelfcraft (backend API + web app) on macOS/Linux and open it in your browser.
#
#   ./scripts/start.sh                 # dev mode
#   ./scripts/start.sh --prod          # optimized build (first build takes ~1-2 min)
#   ./scripts/start.sh --prod --lan    # let devices on your network connect (team mode must be on)
# Options: --api-port N (default 8000)  --web-port N (default 3000)  --no-browser
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROD=0; LAN=0; OPEN_BROWSER=1; API_PORT=8000; WEB_PORT=3000
while [ $# -gt 0 ]; do
  case "$1" in
    --prod) PROD=1 ;;
    --lan) LAN=1 ;;
    --no-browser) OPEN_BROWSER=0 ;;
    --api-port) API_PORT="$2"; shift ;;
    --web-port) WEB_PORT="$2"; shift ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

die()  { printf '\033[31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }
warn() { printf '\033[33mWARNING: %s\033[0m\n' "$*" >&2; }
have() { command -v "$1" >/dev/null 2>&1; }
for d in /opt/homebrew/bin /usr/local/bin; do [ -d "$d" ] && case ":$PATH:" in *":$d:"*) ;; *) PATH="$d:$PATH" ;; esac; done
export PATH

PY="$ROOT/backend/.venv/bin/python"
[ -x "$PY" ] || die "Backend not set up. Run ./scripts/setup.sh first."
[ -d "$ROOT/frontend/node_modules" ] || die "Frontend not set up. Run ./scripts/setup.sh first."

port_busy() {
  if have lsof; then lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
  else "$PY" -c "import socket,sys;s=socket.socket();sys.exit(0 if s.connect_ex(('127.0.0.1',$1))==0 else 1)"; fi
}
port_busy "$API_PORT" && die "Port $API_PORT is already in use (is Shelfcraft already running? run ./scripts/stop.sh)"
port_busy "$WEB_PORT" && die "Port $WEB_PORT is already in use (run ./scripts/stop.sh or pass --web-port)"

# Ollama: start the local server if installed and not running (optional).
if have ollama && ! curl -fsS --max-time 2 http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
  nohup ollama serve >/dev/null 2>&1 &
  echo "Started Ollama (local AI)."
fi

LOGS="$ROOT/data/logs"; mkdir -p "$LOGS"
echo "Starting API on http://127.0.0.1:$API_PORT ..."
( cd "$ROOT/backend" && exec nohup "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT" \
    --timeout-graceful-shutdown 15 >"$LOGS/api-stdout.log" 2>"$LOGS/api-stderr.log" ) &
API_PID=$!

export SHELFCRAFT_API_ORIGIN="http://127.0.0.1:$API_PORT"
WEB_HOST=127.0.0.1
if [ "$LAN" = 1 ]; then
  # The API always stays on 127.0.0.1; only the web app (which proxies /api and /v1) is opened to the LAN,
  # and only when team mode guarantees every request is authenticated.
  TEAM=""
  for _ in $(seq 60); do
    sleep 1
    TEAM="$(curl -fsS --max-time 3 "http://127.0.0.1:$API_PORT/api/auth/status" 2>/dev/null \
      | "$PY" -c 'import json,sys;print(json.load(sys.stdin).get("team_mode"))' 2>/dev/null)" && break || true
  done
  if [ "$TEAM" = "True" ]; then WEB_HOST=0.0.0.0; echo "LAN access enabled (team mode is on)."
  else warn "LAN access refused: enable team mode first (Settings -> Team). Starting on this computer only."; fi
fi

cd "$ROOT/frontend"
if [ "$PROD" = 1 ]; then
  echo "Building web app (production)..."
  npm run build || { kill "$API_PID" 2>/dev/null; die "Build failed"; }
  nohup npm run start -- -p "$WEB_PORT" -H "$WEB_HOST" >"$LOGS/web.log" 2>&1 &
else
  nohup npm run dev -- -p "$WEB_PORT" -H "$WEB_HOST" >"$LOGS/web.log" 2>&1 &
fi
WEB_PID=$!
printf '{"api": %s, "web": %s}\n' "$API_PID" "$WEB_PID" >"$ROOT/data/.pids.json"

echo "Waiting for services..."
OK=0
for _ in $(seq 90); do
  sleep 2
  if curl -fsS --max-time 3 "http://127.0.0.1:$API_PORT/api/health" >/dev/null 2>&1 \
     && curl -fsS --max-time 5 -o /dev/null "http://127.0.0.1:$WEB_PORT"; then OK=1; break; fi
done
[ "$OK" = 1 ] || { warn "Services didn't respond in time. Check data/logs/api-stderr.log and data/logs/web.log"; exit 1; }

URL="http://127.0.0.1:$WEB_PORT"
printf '\033[32mShelfcraft is running: %s\033[0m\n' "$URL"
if [ "$WEB_HOST" = 0.0.0.0 ]; then
  IP="$( (ipconfig getifaddr en0 || ipconfig getifaddr en1 || hostname -I | awk '{print $1}') 2>/dev/null || true)"
  [ -n "$IP" ] && echo "Phone app / teammates on your Wi-Fi: http://$IP:$WEB_PORT"
fi
echo "Stop it with: ./scripts/stop.sh"
if [ "$OPEN_BROWSER" = 1 ]; then
  if have open; then open "$URL"; elif have xdg-open; then xdg-open "$URL" >/dev/null 2>&1 || true; fi
fi
