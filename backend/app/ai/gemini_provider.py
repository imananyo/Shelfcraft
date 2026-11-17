"""Google Gemini API (AI Studio key) — text and vision only.

Image generation (Imagen / Gemini image models) is NOT exposed: as of 2026-11-13 it requires
a billing-linked account, which violates the free-only policy.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import re
import time
from typing import Any

from app.ai.base import (
    Provider,
    ProviderBadResponse,
    ProviderInfo,
    ProviderNotConfigured,
    ProviderRefused,
    ProviderRuntimeConfig,
    ProviderUnavailable,
    TextRequest,
    TextResult,
)
from app.ai.http import request_json

log = logging.getLogger("shelfcraft.gemini")

BASE = "https://generativelanguage.googleapis.com/v1beta"
# Image-output and preview/pro models are excluded to avoid billing-only endpoints.
_BLOCKED_SUBSTRINGS = ("image", "imagen", "veo", "tts", "live", "embedding", "aqa")
AUTO = "auto"
_CACHE_TTL = 12 * 3600
_auto_cache: dict[str, tuple[str, float]] = {}  # key fingerprint -> (model, resolved at)
_retired: set[str] = set()  # models Google told us are gone (this process)


def _fingerprint(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _version(name: str) -> tuple[float, ...]:
    m = re.match(r"gemini-(\d+(?:\.\d+)*)", name)
    return tuple(float(x) for x in m.group(1).split(".")) if m else (0.0,)


def pick_model(models: list[str]) -> str | None:
    """Choose the best free text model from what the key can actually use: newest stable Flash first, then the
    'flash-latest' alias, then stable Flash-Lite, then any non-preview Flash, then anything allowed."""
    usable = [m for m in models if m not in _retired]
    unstable = ("preview", "exp", "thinking", "learnlm", "gemma")
    stable_flash = [m for m in usable if re.fullmatch(r"gemini-\d+(?:\.\d+)*-flash", m)]
    if stable_flash:
        return max(stable_flash, key=_version)
    if "gemini-flash-latest" in usable:
        return "gemini-flash-latest"
    lite = [m for m in usable if re.fullmatch(r"gemini-\d+(?:\.\d+)*-flash-lite", m)]
    if lite:
        return max(lite, key=_version)
    flash = [m for m in usable if "flash" in m and not any(u in m for u in unstable)]
    if flash:
        return max(flash, key=_version)
    rest = [m for m in usable if not any(u in m for u in unstable)] or usable
    return max(rest, key=_version) if rest else None


def pick_backup(models: list[str], current: str) -> str | None:
    """A lighter model to try when the main one is overloaded (HTTP 503 'high demand')."""
    usable = [m for m in models if m not in _retired and m != current]
    if "gemini-flash-lite-latest" in usable:
        return "gemini-flash-lite-latest"
    lite = [m for m in usable if re.fullmatch(r"gemini-\d+(?:\.\d+)*-flash-lite", m)]
    return max(lite, key=_version) if lite else None


def _model_gone(err: ProviderBadResponse) -> bool:
    msg = err.message.lower()
    return "http 404" in msg and ("no longer available" in msg or "not_found" in msg or "not found" in msg)


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
        # Google retires model versions for new keys (e.g. gemini-2.5-flash in Nov 2026), so the model is picked
        # from the key's own model list unless the user chose one.
        default_text_model=AUTO,
        vision=True,
    )

    def allowed_model(self, model: str) -> bool:
        return model.startswith("gemini") and not any(s in model for s in _BLOCKED_SUBSTRINGS)

    def _key(self, cfg: ProviderRuntimeConfig) -> str:
        if not cfg.api_key:
            raise ProviderNotConfigured(self.info.name, "API key not set")
        return cfg.api_key

    def auto_model(self, cfg: ProviderRuntimeConfig, *, refresh: bool = False) -> str:
        key = self._key(cfg)
        fp = _fingerprint(key)
        hit = _auto_cache.get(fp)
        if hit and not refresh and time.time() - hit[1] < _CACHE_TTL and hit[0] not in _retired:
            return hit[0]
        model = pick_model(self.list_models(cfg))
        if not model:
            raise ProviderBadResponse(self.info.name, "your API key has no free Gemini text model available")
        _auto_cache[fp] = (model, time.time())
        return model

    def generate_text(self, req: TextRequest, cfg: ProviderRuntimeConfig) -> TextResult:
        requested = req.model or cfg.text_model
        model = requested if requested and requested != AUTO else self.auto_model(cfg)
        try:
            return self._generate(req, cfg, model)
        except ProviderUnavailable as e:
            # Google answers 503 "high demand" per model; the Lite model usually still has capacity.
            if "HTTP 503" not in e.message:
                raise
            backup = pick_backup(self.list_models(cfg), model)
            if not backup:
                raise
            log.warning("Gemini model %s is overloaded (HTTP 503); trying %s", model, backup)
            return self._generate(req, cfg, backup)
        except ProviderBadResponse as e:
            if not _model_gone(e):
                raise
            # The model was retired by Google: switch to the best model this key can use and retry once.
            _retired.add(model)
            replacement = self.auto_model(cfg, refresh=True)
            if replacement == model:
                raise
            log.warning("Gemini model %s is no longer available; switched to %s", model, replacement)
            if cfg.text_model == model:
                _forget_saved_model(model)
            return self._generate(req, cfg, replacement)

    def _generate(self, req: TextRequest, cfg: ProviderRuntimeConfig, model: str) -> TextResult:
        key = self._key(cfg)
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


def _forget_saved_model(model: str) -> None:
    """A retired model saved in Settings would fail forever: reset that setting to automatic."""
    from app.ai.model_health import forget_saved_model

    forget_saved_model("gemini", model)
