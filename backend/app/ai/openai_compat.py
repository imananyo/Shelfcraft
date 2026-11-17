"""Base adapter for OpenAI-compatible chat-completions APIs (Groq, OpenRouter, Mistral)."""
from __future__ import annotations

import base64
import logging
import time
from typing import Any

from app.ai import model_health as mh
from app.ai.base import (
    Provider,
    ProviderBadResponse,
    ProviderNotConfigured,
    ProviderRefused,
    ProviderRuntimeConfig,
    ProviderUnavailable,
    TextRequest,
    TextResult,
)
from app.ai.http import request_json

log = logging.getLogger("shelfcraft.ai")
MAX_MODEL_ATTEMPTS = 3  # requested model + up to two alternatives (free quotas: don't burn many requests)


class OpenAICompatProvider(Provider):
    base_url: str = ""
    supports_json_mode: bool = True

    def _headers(self, cfg: ProviderRuntimeConfig) -> dict[str, str]:
        if not cfg.api_key:
            raise ProviderNotConfigured(self.info.name, "API key not set")
        return {"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"}

    def _resolve_model(self, req_model: str | None, cfg: ProviderRuntimeConfig) -> str:
        model = req_model or cfg.text_model or self.info.default_text_model
        if not model or model == mh.AUTO:
            if self.info.paid:
                raise ProviderNotConfigured(self.info.name, "choose a model for this paid provider in Settings")
            model = self.auto_model(cfg)
        if not self.allowed_model(model):
            raise ProviderRefused(self.info.name, f"model '{model}' is not on the free allow-list")
        return model

    def ranked_models(self, cfg: ProviderRuntimeConfig) -> list[str]:
        return mh.rank_models(self.list_models(cfg), self.info.name)

    def auto_model(self, cfg: ProviderRuntimeConfig, *, refresh: bool = False) -> str:
        if not refresh and (hit := mh.cached(self.info.name, cfg.api_key)):
            return hit
        ranked = self.ranked_models(cfg)
        if not ranked:
            raise ProviderNotConfigured(self.info.name, "no suitable free chat model is available to this key")
        mh.remember(self.info.name, cfg.api_key, ranked[0])
        return ranked[0]

    def generate_text(self, req: TextRequest, cfg: ProviderRuntimeConfig) -> TextResult:
        model = self._resolve_model(req.model, cfg)
        if self.info.paid:  # never switch a paid provider to another (possibly pricier) model on our own
            return self._chat(req, cfg, model)
        tried: list[str] = []
        ranked: list[str] | None = None
        while True:
            tried.append(model)
            try:
                return self._chat(req, cfg, model)
            except ProviderBadResponse as e:
                if not mh.model_gone(e.message) or len(tried) >= MAX_MODEL_ATTEMPTS:
                    raise
                # Retired / decommissioned / no longer free: never use it again, reset a saved setting.
                mh.mark_retired(self.info.name, model)
                if cfg.text_model == model:
                    mh.forget_saved_model(self.info.name, model)
                reason, err = "is no longer available", e
            except ProviderUnavailable as e:
                if "HTTP 503" not in e.message or len(tried) >= MAX_MODEL_ATTEMPTS:
                    raise
                reason, err = "is overloaded (HTTP 503)", e
            ranked = ranked if ranked is not None else self.ranked_models(cfg)
            nxt = next((m for m in ranked if m not in tried and not mh.is_retired(self.info.name, m)), None)
            if not nxt:
                raise err
            log.warning("%s model %s %s; trying %s", self.info.name, model, reason, nxt)
            if reason.startswith("is no"):
                mh.remember(self.info.name, cfg.api_key, nxt)
            model = nxt

    def extra_body(self, model: str) -> dict[str, Any]:
        """Provider-specific request options (override)."""
        return {}

    def _chat(self, req: TextRequest, cfg: ProviderRuntimeConfig, model: str) -> TextResult:
        messages: list[dict[str, Any]] = []
        if req.system:
            messages.append({"role": "system", "content": req.system})
        if req.images:
            content: list[dict[str, Any]] = [{"type": "text", "text": req.prompt}]
            for img in req.images[:4]:
                b64 = base64.b64encode(img).decode()
                content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": req.prompt})
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
        }
        if req.json_mode and self.supports_json_mode:
            body["response_format"] = {"type": "json_object"}
        body.update(self.extra_body(model))
        t0 = time.perf_counter()
        data = request_json(
            self.info.name, "POST", f"{self.base_url}/chat/completions",
            headers=self._headers(cfg), json_body=body, secrets=[cfg.api_key],
        )
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise ProviderBadResponse(self.info.name, "unexpected response shape") from None
        usage = data.get("usage") or {}
        return TextResult(
            text=text, provider=self.info.name, model=model,
            input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens"),
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )

    def list_models(self, cfg: ProviderRuntimeConfig) -> list[str]:
        data = request_json(self.info.name, "GET", f"{self.base_url}/models",
                            headers=self._headers(cfg), secrets=[cfg.api_key], timeout=20.0)
        ids = [m.get("id") for m in data.get("data", []) if m.get("id")]
        return [i for i in ids if self.allowed_model(i)]
