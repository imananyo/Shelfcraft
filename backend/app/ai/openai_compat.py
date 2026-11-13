"""Base adapter for OpenAI-compatible chat-completions APIs (Groq, OpenRouter, Mistral)."""
from __future__ import annotations

import base64
import time
from typing import Any

from app.ai.base import (
    Provider,
    ProviderBadResponse,
    ProviderNotConfigured,
    ProviderRefused,
    ProviderRuntimeConfig,
    TextRequest,
    TextResult,
)
from app.ai.http import request_json


class OpenAICompatProvider(Provider):
    base_url: str = ""
    supports_json_mode: bool = True

    def _headers(self, cfg: ProviderRuntimeConfig) -> dict[str, str]:
        if not cfg.api_key:
            raise ProviderNotConfigured(self.info.name, "API key not set")
        return {"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"}

    def _resolve_model(self, req_model: str | None, cfg: ProviderRuntimeConfig) -> str:
        model = req_model or cfg.text_model or self.info.default_text_model
        if not model:
            raise ProviderNotConfigured(self.info.name, "no model selected")
        if not self.allowed_model(model):
            raise ProviderRefused(self.info.name, f"model '{model}' is not on the free allow-list")
        return model

    def generate_text(self, req: TextRequest, cfg: ProviderRuntimeConfig) -> TextResult:
        model = self._resolve_model(req.model, cfg)
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
