"""Local text-to-image / image-to-image on CPU via Hugging Face diffusers (optional install).

Default model: stabilityai/sd-turbo (1–4 steps, 512 px native) — the only class of diffusion
model that is practical on a 4-core laptop CPU without a GPU. The pipeline is loaded lazily
once and kept in memory; a lock serializes generation (one CPU-heavy job at a time).
"""
from __future__ import annotations

import io
import logging
import threading
import time
from typing import Any

from app.ai.base import (
    ImageRequest,
    ImageResult,
    Provider,
    ProviderInfo,
    ProviderRuntimeConfig,
    ProviderUnavailable,
)

log = logging.getLogger("shelfcraft.ai.local_diffusion")
_lock = threading.Lock()
_pipes: dict[str, Any] = {}


def diffusers_available() -> bool:
    try:
        import diffusers  # noqa: F401
        import torch  # noqa: F401
        return True
    except Exception:  # noqa: BLE001 - optional dependency
        return False


class LocalDiffusionProvider(Provider):
    info = ProviderInfo(
        name="local_diffusion",
        label="Local diffusion (CPU)",
        kinds=("image",),
        local=True,
        free_tier_verified=True,
        verified_on="2026-11-13",
        source_url="https://huggingface.co/stabilityai/sd-turbo",
        limits_note="CPU only on this machine: first load ~30–90 s; then roughly 5–30 s per 512×512 image "
        "at 1–4 steps. Larger sizes are upscaled, not generated natively.",
        privacy_note="Local — nothing leaves this computer.",
        license_note="sd-turbo weights: Stability AI license — treat as personal/non-commercial until you "
        "verify the model card terms for your use.",
        requires_key=False,
        default_image_model="stabilityai/sd-turbo",
    )

    def is_configured(self, cfg: ProviderRuntimeConfig) -> bool:
        return diffusers_available()

    def _pipe(self, model: str, img2img: bool) -> Any:
        key = f"{model}|{'i2i' if img2img else 't2i'}"
        if key in _pipes:
            return _pipes[key]
        import torch
        from diffusers import AutoPipelineForImage2Image, AutoPipelineForText2Image

        from app.config import get_settings

        torch.set_num_threads(max(1, (torch.get_num_threads() or 4)))
        cache = str(get_settings().models_dir / "hf")
        t0 = time.perf_counter()
        base_key = f"{model}|t2i"
        if img2img and base_key in _pipes:
            pipe = AutoPipelineForImage2Image.from_pipe(_pipes[base_key])
        else:
            cls = AutoPipelineForImage2Image if img2img else AutoPipelineForText2Image
            pipe = cls.from_pretrained(model, torch_dtype=torch.float32, cache_dir=cache)
        pipe.set_progress_bar_config(disable=True)
        _pipes[key] = pipe
        log.info("loaded %s in %.1fs", key, time.perf_counter() - t0)
        return pipe

    def generate_image(self, req: ImageRequest, cfg: ProviderRuntimeConfig) -> ImageResult:
        if not diffusers_available():
            raise ProviderUnavailable(self.info.name, "diffusers/torch not installed (run scripts/install-local-image-model.ps1)")
        import torch
        from PIL import Image

        model = req.model or cfg.image_model or self.info.default_image_model or ""
        # Generate at a CPU-friendly native size, preserving aspect ratio; caller upscales.
        scale = 512 / max(req.width, req.height)
        w = max(256, int(req.width * scale) // 64 * 64)
        h = max(256, int(req.height * scale) // 64 * 64)
        seed = req.seed if req.seed is not None else int(time.time()) % 2**31
        gen = torch.Generator("cpu").manual_seed(seed)
        t0 = time.perf_counter()
        with _lock:
            try:
                if req.init_image:
                    init = Image.open(io.BytesIO(req.init_image)).convert("RGB").resize((w, h))
                    pipe = self._pipe(model, img2img=True)
                    steps = max(2, req.steps or 2)
                    strength = min(0.95, max(0.3, req.strength))
                    if steps * strength < 1:
                        steps = int(1 / strength) + 1
                    out = pipe(prompt=req.prompt, image=init, num_inference_steps=steps,
                               strength=strength, guidance_scale=0.0, generator=gen)
                else:
                    pipe = self._pipe(model, img2img=False)
                    out = pipe(prompt=req.prompt, width=w, height=h, num_inference_steps=req.steps or 2,
                               guidance_scale=0.0, generator=gen)
            except Exception as e:  # noqa: BLE001 - surface as provider failure
                raise ProviderUnavailable(self.info.name, f"{type(e).__name__}: {e}") from None
        img = out.images[0]
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return ImageResult(image_png=buf.getvalue(), provider=self.info.name, model=model, seed=seed,
                           latency_ms=int((time.perf_counter() - t0) * 1000),
                           meta={"native_size": [w, h]})

    def list_models(self, cfg: ProviderRuntimeConfig) -> list[str]:
        if not diffusers_available():
            raise ProviderUnavailable(self.info.name, "diffusers/torch not installed")
        return ["stabilityai/sd-turbo", "stabilityai/sdxl-turbo"]
