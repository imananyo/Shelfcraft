"""Google Gemini API (AI Studio key) — text and vision only.

Image generation (Imagen / Gemini image models) is NOT exposed: as of 2026-11-13 it requires
a billing-linked account, which violates the free-only policy.
"""
from __future__ import annotations

import base64
import time
from typing import Any

from app.ai.base import (
    Provider,
    ProviderBadResponse,
    ProviderInfo,
    ProviderNotConfigured,
    ProviderRefused,
    ProviderRuntimeConfig,
    TextRequest,
    TextResult,
)
from app.ai.http import request_json

BASE = "https://generativelanguage.googleapis.com/v1beta"
# Image-output and preview/pro models are excluded to avoid billing-only endpoints.
_BLOCKED_SUBSTRINGS = ("image", "imagen", "veo", "tts", "live", "embedding", "aqa")


class GeminiProvider(Provider):
    info = ProviderInfo(
        name="gemini",
        label="Google Gemini (AI Studio free tier)",
        kinds=("text",),
        local=False,
        free_tier_verified=True,
        verified_on="2026-11-13",
        source_url="https://ai.google.dev/gemini-api/docs/rate-limits",
        limits_note="Free tier is per-project RPM/RPD/TPM, shown in AI Studio; RPD resets at midnight "
        "Pacific. Google describes the free tier as best-effort and subject to change. "
        "Image generation requires billing → not used.",
        privacy_note="On the free tier Google may use prompts and outputs to improve its products. "
        "Do not send confidential data.",
        default_text_model="gemini-2.5-flash",
        vision=True,
    )

    def allowed_model(self, model: str) -> bool:
        return model.startswith("gemini") and not any(s in model for s in _BLOCKED_SUBSTRINGS)

    def _key(self, cfg: ProviderRuntimeConfig) -> str:
        if not cfg.api_key:
            raise ProviderNotConfigured(self.info.name, "API key not set")
        return cfg.api_key

    def generate_text(self, req: TextRequest, cfg: ProviderRuntimeConfig) -> TextResult:
        key = self._key(cfg)
        model = req.model or cfg.text_model or self.info.default_text_model or ""
        if not self.allowed_model(model):
            raise ProviderRefused(self.info.name, f"model '{model}' is not on the free allow-list")
        parts: list[dict[str, Any]] = [{"text": req.prompt}]
        for img in req.images[:4]:
            parts.append({"inline_data": {"mime_type": "image/png", "data": base64.b64encode(img).decode()}})
        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": req.temperature, "maxOutputTokens": req.max_tokens},
        }
        if req.system:
            body["systemInstruction"] = {"parts": [{"text": req.system}]}
        if req.json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"
        t0 = time.perf_counter()
        data = request_json(
            self.info.name, "POST", f"{BASE}/models/{model}:generateContent",
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            json_body=body, secrets=[key],
        )
        try:
            cand = data["candidates"][0]
            text = "".join(p.get("text", "") for p in cand["content"]["parts"])
        except (KeyError, IndexError, TypeError):
            reason = (data.get("promptFeedback") or {}).get("blockReason")
            raise ProviderBadResponse(self.info.name, f"no content returned{f' ({reason})' if reason else ''}") from None
        usage = data.get("usageMetadata") or {}
        return TextResult(
            text=text, provider=self.info.name, model=model,
            input_tokens=usage.get("promptTokenCount"), output_tokens=usage.get("candidatesTokenCount"),
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )

    def list_models(self, cfg: ProviderRuntimeConfig) -> list[str]:
        key = self._key(cfg)
        data = request_json(self.info.name, "GET", f"{BASE}/models?pageSize=200",
                            headers={"x-goog-api-key": key}, secrets=[key], timeout=20.0)
        out = []
        for m in data.get("models", []):
            name = m.get("name", "").removeprefix("models/")
            if "generateContent" in m.get("supportedGenerationMethods", []) and self.allowed_model(name):
                out.append(name)
        return sorted(out)
