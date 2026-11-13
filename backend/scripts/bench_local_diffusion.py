"""Benchmark local SD-Turbo on this machine's CPU. Usage: python scripts/bench_local_diffusion.py"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ai.base import ImageRequest, ProviderRuntimeConfig  # noqa: E402
from app.ai.local_diffusion_provider import LocalDiffusionProvider  # noqa: E402
from app.config import get_settings  # noqa: E402

get_settings().ensure_dirs()
p = LocalDiffusionProvider()
cfg = ProviderRuntimeConfig(enabled=True, api_key=None, extra={}, text_model=None, image_model=None)
out_dir = get_settings().data_dir / "bench"
out_dir.mkdir(parents=True, exist_ok=True)
prompts = [
    "studio product photo of a ceramic coffee mug on a marble countertop, soft morning light, shallow depth of field",
    "minimal pastel podium with soft shadows, product photography background, empty, high detail",
    "cozy modern kitchen interior, blurred background, warm light, lifestyle photography backdrop",
]
t_all = time.perf_counter()
for i, prompt in enumerate(prompts):
    t0 = time.perf_counter()
    r = p.generate_image(ImageRequest(prompt=prompt, width=512, height=512, steps=2, seed=42 + i), cfg)
    (out_dir / f"bench_{i}.png").write_bytes(r.image_png)
    print(f"image {i}: {time.perf_counter() - t0:.1f}s wall (provider {r.latency_ms} ms) size={r.meta}", flush=True)
print(f"total {time.perf_counter() - t_all:.1f}s")
