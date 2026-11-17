"""Optional PAID providers — the model stack Pixii advertises ("Nano Banana" and GPT).

These cost money per call on YOUR account. They are never part of the automatic free fallback chain:
they run only when (1) "Allow paid providers" is switched on in Settings, (2) the provider is enabled with
your key, and (3) you pick it explicitly for a generation. The free/local providers remain the defaults.
"""
from __future__ import annotations

import base64
import io
import time
from typing import Any

import httpx

from app.ai.base import (
    ImageRequest,
    ImageResult,
    Provider,
    ProviderBadResponse,
    ProviderInfo,
    ProviderNotConfigured,
    ProviderRuntimeConfig,
    TextRequest,
    TextResult,
)
from app.ai.http import DEFAULT_TIMEOUT, request_json
from app.ai.openai_compat import OpenAICompatProvider

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
OPENAI_BASE = "https://api.openai.com/v1"


def _to_png(data: bytes) -> bytes:
    from PIL import Image

    im = Image.open(io.BytesIO(data))
    if im.format == "PNG":
        return data
    out = io.BytesIO()
    im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB").save(out, "PNG")
    return out.getvalue()


def _aspect(w: int, h: int) -> str:
    r = w / max(h, 1)
    options = {"1:1": 1, "4:5": 0.8, "5:4": 1.25, "3:4": 0.75, "4:3": 4 / 3, "2:3": 2 / 3, "3:2": 1.5,
               "9:16": 9 / 16, "16:9": 16 / 9, "21:9": 21 / 9}
    return min(options, key=lambda k: abs(options[k] - r))


class NanoBananaProvider(Provider):
    """Google Gemini image models: gemini-2.5-flash-image ("Nano Banana") / gemini-3-pro-image-preview ("Nano Banana Pro")."""

    info = ProviderInfo(
        name="nano_banana",
        label="Google Nano Banana (Gemini image) — paid",
        kinds=("image",),
        local=False,
        free_tier_verified=False,
        paid=True,
        verified_on="2026-11-16",
        source_url="https://ai.google.dev/gemini-api/docs/image-generation",
        limits_note="Billed per image on your Google AI Studio / Vertex billing account. Check current pricing at "
                    "ai.google.dev/pricing before use.",
        privacy_note="Prompts and product photos are sent to Google.",
        default_image_model="gemini-2.5-flash-image",
    )

    def allowed_model(self, model: str) -> bool:
        return model.startswith("gemini") and "image" in model

    def generate_image(self, req: ImageRequest, cfg: ProviderRuntimeConfig) -> ImageResult:
        if not cfg.api_key:
            raise ProviderNotConfigured(self.info.name, "API key not set")
        model = req.model or cfg.image_model or self.info.default_image_model or ""
        prompt = req.prompt + (f"\nAvoid: {req.negative_prompt}" if req.negative_prompt else "")
        parts: list[dict[str, Any]] = [{"text": prompt}]
        if req.init_image:  # image editing: keep the product, follow the prompt
            parts.append({"inline_data": {"mime_type": "image/png", "data": base64.b64encode(req.init_image).decode()}})
        body = {"contents": [{"role": "user", "parts": parts}],
                "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": _aspect(req.width, req.height)}}}
        t0 = time.perf_counter()
        data = request_json(self.info.name, "POST", f"{GEMINI_BASE}/models/{model}:generateContent",
                            headers={"x-goog-api-key": cfg.api_key, "Content-Type": "application/json"},
                            json_body=body, secrets=[cfg.api_key])
        try:
            for part in data["candidates"][0]["content"]["parts"]:
                blob = part.get("inlineData") or part.get("inline_data")
                if blob and blob.get("data"):
                    png = _to_png(base64.b64decode(blob["data"]))
                    return ImageResult(image_png=png, provider=self.info.name, model=model, seed=req.seed,
                                       latency_ms=int((time.perf_counter() - t0) * 1000), meta={"paid": True})
        except (KeyError, IndexError, TypeError):
            pass
        reason = (data.get("promptFeedback") or {}).get("blockReason") if isinstance(data, dict) else None
        raise ProviderBadResponse(self.info.name, f"no image returned{f' ({reason})' if reason else ''}")

    def list_models(self, cfg: ProviderRuntimeConfig) -> list[str]:
        if not cfg.api_key:
            raise ProviderNotConfigured(self.info.name, "API key not set")
        data = request_json(self.info.name, "GET", f"{GEMINI_BASE}/models?pageSize=200",
                            headers={"x-goog-api-key": cfg.api_key}, secrets=[cfg.api_key], timeout=20.0)
        names = [m.get("name", "").removeprefix("models/") for m in data.get("models", [])]
        return sorted(n for n in names if self.allowed_model(n))


class OpenAIProvider(OpenAICompatProvider):
    """OpenAI GPT text + gpt-image-1 images (and image edits from your product photo)."""

    base_url = OPENAI_BASE
    info = ProviderInfo(
        name="openai",
        label="OpenAI GPT + GPT Image — paid",
        kinds=("text", "image"),
        local=False,
        free_tier_verified=False,
        paid=True,
        verified_on="2026-11-16",
        source_url="https://platform.openai.com/docs/pricing",
        limits_note="Billed per token / per image on your OpenAI account. Check current pricing before use.",
        privacy_note="Prompts and product photos are sent to OpenAI.",
        default_text_model="gpt-5-mini",
        default_image_model="gpt-image-1",
        vision=True,
    )

    def generate_text(self, req: TextRequest, cfg: ProviderRuntimeConfig) -> TextResult:
        model = self._resolve_model(req.model, cfg)
        if not (model.startswith("gpt-5") or model.startswith("o")):
            return super().generate_text(req, cfg)
        # Reasoning models: no custom temperature, max_completion_tokens instead of max_tokens.
        messages: list[dict[str, Any]] = []
        if req.system:
            messages.append({"role": "system", "content": req.system})
        content: Any = req.prompt
        if req.images:
            content = [{"type": "text", "text": req.prompt}] + [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64.b64encode(i).decode()}"}}
                for i in req.images[:4]]
        messages.append({"role": "user", "content": content})
        body: dict[str, Any] = {"model": model, "messages": messages, "max_completion_tokens": max(req.max_tokens, 4000)}
        if req.json_mode:
            body["response_format"] = {"type": "json_object"}
        t0 = time.perf_counter()
        data = request_json(self.info.name, "POST", f"{self.base_url}/chat/completions", headers=self._headers(cfg),
                            json_body=body, secrets=[cfg.api_key])
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise ProviderBadResponse(self.info.name, "unexpected response shape") from None
        usage = data.get("usage") or {}
        return TextResult(text=text, provider=self.info.name, model=model, input_tokens=usage.get("prompt_tokens"),
                          output_tokens=usage.get("completion_tokens"), latency_ms=int((time.perf_counter() - t0) * 1000))

    def generate_image(self, req: ImageRequest, cfg: ProviderRuntimeConfig) -> ImageResult:
        if not cfg.api_key:
            raise ProviderNotConfigured(self.info.name, "API key not set")
        model = req.model if (req.model or "").startswith(("gpt-image", "dall-e")) else (cfg.image_model or self.info.default_image_model)
        r = req.width / max(req.height, 1)
        size = "1024x1024" if 0.8 <= r <= 1.25 else ("1536x1024" if r > 1 else "1024x1536")
        prompt = req.prompt + (f"\nAvoid: {req.negative_prompt}" if req.negative_prompt else "")
        t0 = time.perf_counter()
        if req.init_image:
            try:
                with httpx.Client(timeout=DEFAULT_TIMEOUT) as c:
                    resp = c.post(f"{self.base_url}/images/edits", headers={"Authorization": f"Bearer {cfg.api_key}"},
                                  data={"model": model, "prompt": prompt, "size": size, "n": "1"},
                                  files={"image[]": ("product.png", req.init_image, "image/png")})
            except httpx.HTTPError as e:
                raise ProviderBadResponse(self.info.name, f"network error: {type(e).__name__}") from None
            if resp.status_code >= 400:
                raise ProviderBadResponse(self.info.name, f"HTTP {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
        else:
            data = request_json(self.info.name, "POST", f"{self.base_url}/images/generations", headers=self._headers(cfg),
                                json_body={"model": model, "prompt": prompt, "size": size, "n": 1}, secrets=[cfg.api_key])
        try:
            png = _to_png(base64.b64decode(data["data"][0]["b64_json"]))
        except (KeyError, IndexError, TypeError):
            raise ProviderBadResponse(self.info.name, "no image returned") from None
        return ImageResult(image_png=png, provider=self.info.name, model=model, seed=req.seed,
                           latency_ms=int((time.perf_counter() - t0) * 1000), meta={"paid": True, "size": size})

    def list_models(self, cfg: ProviderRuntimeConfig) -> list[str]:
        data = request_json(self.info.name, "GET", f"{self.base_url}/models", headers=self._headers(cfg),
                            secrets=[cfg.api_key], timeout=20.0)
        ids = [m.get("id") for m in data.get("data", []) if m.get("id")]
        return sorted(i for i in ids if i.startswith(("gpt-", "o", "dall-e")))
