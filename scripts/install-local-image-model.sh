#!/usr/bin/env bash
# Optional: install local image generation (PyTorch + diffusers) and pre-download SD-Turbo.
# Downloads ~250 MB-1 GB of Python wheels and ~2.5 GB of model weights to data/models/hf.
# sd-turbo weights are under a Stability AI license - treat as personal/non-commercial until you
# verify the terms on https://huggingface.co/stabilityai/sd-turbo for your use.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/backend/.venv/bin/python"
[ -x "$PY" ] || { echo "Run ./scripts/setup.sh first." >&2; exit 1; }

echo "Installing PyTorch + diffusers..."
if [ "$(uname -s)" = "Darwin" ]; then
  "$PY" -m pip install torch            # macOS wheels are CPU/Apple-GPU builds already
else
  "$PY" -m pip install torch --index-url https://download.pytorch.org/whl/cpu   # small CPU-only build
fi
"$PY" -m pip install "diffusers>=0.31" "transformers>=4.46" accelerate safetensors

echo "Downloading SD-Turbo and running a benchmark (first run takes several minutes)..."
( cd "$ROOT/backend" && "$PY" scripts/bench_local_diffusion.py )
echo "Done. Enable 'Local diffusion (CPU)' in Settings -> AI providers (it is enabled automatically on a fresh install)."
