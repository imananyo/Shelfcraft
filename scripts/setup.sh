#!/usr/bin/env bash
# One-time setup for Shelfcraft on macOS and Linux: Python venv, backend deps, frontend deps, .env.
# Safe to re-run. Installs system software only with --install-prereqs.
#
#   ./scripts/setup.sh
#   ./scripts/setup.sh --install-prereqs --pull-ollama-models --with-local-image-model
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_PREREQS=0; PULL_MODELS=0; WITH_IMAGE=0
for a in "$@"; do
  case "$a" in
    --install-prereqs) INSTALL_PREREQS=1 ;;
    --pull-ollama-models) PULL_MODELS=1 ;;
    --with-local-image-model) WITH_IMAGE=1 ;;
    -h|--help) sed -n '2,6p' "$0"; exit 0 ;;
    *) echo "Unknown option: $a" >&2; exit 2 ;;
  esac
done

step() { printf '\n\033[36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[33mWARNING: %s\033[0m\n' "$*" >&2; }
die()  { printf '\033[31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }
OS="$(uname -s)"

install_prereqs() {
  step "Installing prerequisites (free software; you may be asked for your password)"
  if [ "$OS" = "Darwin" ]; then
    have brew || die "Homebrew is required on macOS. Install it from https://brew.sh then re-run."
    brew install python@3.12 node ffmpeg
    brew install ollama || warn "Could not install Ollama with Homebrew; download it from https://ollama.com/download"
  elif have apt-get; then
    sudo apt-get update
    sudo apt-get install -y python3 python3-venv python3-dev build-essential nodejs npm ffmpeg espeak-ng \
      fonts-dejavu-core curl
    # Python 3.12 is the default on Ubuntu 24.04+/Debian 13; older releases may not have it.
    sudo apt-get install -y python3.12 python3.12-venv 2>/dev/null || true
  elif have dnf; then
    sudo dnf install -y python3.12 python3-devel gcc gcc-c++ nodejs npm espeak-ng dejavu-sans-fonts curl
    sudo dnf install -y ffmpeg 2>/dev/null || sudo dnf install -y ffmpeg-free \
      || warn "Install FFmpeg yourself (Fedora: enable RPM Fusion, then 'sudo dnf install ffmpeg')."
  elif have pacman; then
    sudo pacman -S --needed --noconfirm python nodejs npm ffmpeg espeak-ng ttf-dejavu base-devel curl
  elif have zypper; then
    sudo zypper install -y python312 python312-devel nodejs npm ffmpeg espeak-ng dejavu-fonts gcc-c++ curl
  else
    die "Unknown package manager. Install Python 3.12, Node.js 20+, FFmpeg, espeak-ng and Ollama yourself."
  fi
  if [ "$OS" = "Linux" ] && ! have ollama; then
    echo "Installing Ollama with its official installer (https://ollama.com/install.sh)..."
    curl -fsSL https://ollama.com/install.sh | sh || warn "Ollama install failed; see https://ollama.com/download"
  fi
}

[ "$INSTALL_PREREQS" = 1 ] && install_prereqs
# Homebrew's bin dir may not be on PATH in non-login shells.
for d in /opt/homebrew/bin /usr/local/bin; do [ -d "$d" ] && case ":$PATH:" in *":$d:"*) ;; *) PATH="$d:$PATH" ;; esac; done

step "Checking prerequisites"
PY=""
for c in python3.12 python3.11 python3.13 python3; do
  if have "$c"; then
    v="$("$c" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null || true)"
    case "$v" in 3.11|3.12|3.13) PY="$(command -v "$c")"; break ;; esac
  fi
done
[ -n "$PY" ] || die "Python 3.12 not found (3.11-3.13 also work). Install it, or re-run with --install-prereqs."
PYV="$("$PY" -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
[ "$PYV" = "3.12" ] || warn "Using Python $PYV. Python 3.12 is the tested version."
have node || die "Node.js not found. Install Node 20+ (https://nodejs.org) or re-run with --install-prereqs."
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
[ "$NODE_MAJOR" -ge 20 ] || die "Node.js $(node --version) is too old; Shelfcraft needs Node 20+ (https://nodejs.org or nvm)."
echo "Python: $PY ($PYV)"
echo "Node:   $(node --version)"
have ffmpeg && echo "FFmpeg: found" || warn "FFmpeg not found - video export is unavailable until it is installed."
have ollama && echo "Ollama: found" || warn "Ollama not found - local text AI unavailable (hosted free tiers can still be configured)."
if [ "$OS" = "Linux" ] && ! have espeak-ng && ! have espeak; then
  warn "espeak-ng not found - offline voiceover for videos is unavailable (install the 'espeak-ng' package)."
fi

step "Backend: virtual environment + dependencies"
VENV="$ROOT/backend/.venv"
VPY="$VENV/bin/python"
if [ -d "$VENV" ] && [ ! -x "$VPY" ]; then
  warn "backend/.venv was created on another OS (e.g. Windows); recreating it."
  rm -rf "$VENV"
fi
[ -x "$VPY" ] || "$PY" -m venv "$VENV" || die "Could not create a virtual environment (Debian/Ubuntu: sudo apt install python3-venv)."
"$VPY" -m pip install --upgrade pip --quiet
"$VPY" -m pip install -r "$ROOT/backend/requirements.txt"
# OCR engine for "image -> layers" (no-deps: keeps opencv-python-headless instead of pulling opencv-python)
"$VPY" -m pip install --quiet --no-deps rapidocr-onnxruntime
"$VPY" -c "import onnxruntime, rembg; print('onnxruntime OK')"

step "Backend: environment file"
if [ ! -f "$ROOT/backend/.env" ]; then
  cp "$ROOT/backend/.env.example" "$ROOT/backend/.env"
  echo "Created backend/.env (all providers optional)."
fi

step "Frontend: npm install"
# A node_modules copied from Windows holds Windows-only native binaries (Next.js SWC, Tailwind, sharp) and npm
# does not always replace them, so the web app would fail to start. Reinstall from scratch in that case.
if compgen -G "$ROOT/frontend/node_modules/@next/swc-win32-*" >/dev/null; then
  warn "frontend/node_modules was copied from Windows; reinstalling it for this computer."
  rm -rf "$ROOT/frontend/node_modules"
fi
( cd "$ROOT/frontend" && npm install --no-fund --no-audit )

chmod +x "$ROOT"/scripts/*.sh 2>/dev/null || true
[ "$WITH_IMAGE" = 1 ] && "$ROOT/scripts/install-local-image-model.sh"
if [ "$PULL_MODELS" = 1 ]; then
  if have ollama; then
    step "Pulling local Ollama models (qwen2.5:3b ~1.9 GB, nomic-embed-text ~270 MB)"
    curl -fsS http://127.0.0.1:11434/api/version >/dev/null 2>&1 || { (ollama serve >/dev/null 2>&1 &); sleep 3; }
    ollama pull qwen2.5:3b
    ollama pull nomic-embed-text
  else
    warn "Skipping model download: Ollama is not installed."
  fi
fi

printf '\n\033[32mSetup complete. Start Shelfcraft with:  ./scripts/start.sh\033[0m\n'
