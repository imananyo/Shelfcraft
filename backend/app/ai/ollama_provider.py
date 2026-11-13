"""Ollama — local LLM inference. No key, no data leaves the machine."""
from __future__ import annotations

import base64
import time
from typing import Any

import httpx

from app.ai.base import (
    Provider,
    ProviderBadResponse,
    ProviderInfo,
    ProviderNotConfigured,
    ProviderRuntimeConfig,
    TextRequest,
    TextResult,
)
from app.ai.http import request_json


class OllamaProvider(Provider):
    info = ProviderInfo(
        name="ollama",
        label="Ollama (local)",
        kinds=("text",),
        local=True,
        free_tier_verified=True,
        verified_on="2026-11-13",
        source_url="https://github.com/ollama/ollama",
        limits_note="Runs on your CPU. A 3B model generates roughly 5–15 tokens/s on this laptop; "
        "long outputs take 1–3 minutes.",
        privacy_note="Local — prompts never leave this computer.",
        license_note="Ollama: MIT. Model licenses vary (qwen2.5:3b — Qwen Research License; "
        "llama3.2 — Llama 3.2 Community License). Check before commercial use.",
        requires_key=False,
        default_text_model="qwen2.5:3b",
    )

    _reachable_cache: dict[str, tuple[float, bool]] = {}

    def _base(self, cfg: ProviderRuntimeConfig) -> str:
        return (cfg.extra.get("base_url") or "http://127.0.0.1:11434").rstrip("/")

    def is_configured(self, cfg: ProviderRuntimeConfig) -> bool:
        """'Configured' for a local server means it is actually running (cached for 15 s)."""
        base = self._base(cfg)
        now = time.monotonic()
        cached = self._reachable_cache.get(base)
        if cached and now - cached[0] < 15:
            return cached[1]
        try:
            ok = httpx.get(f"{base}/api/version", timeout=1.0).status_code == 200
        except httpx.HTTPError:
            ok = False
        self._reachable_cache[base] = (now, ok)
        return ok

    def generate_text(self, req: TextRequest, cfg: ProviderRuntimeConfig) -> TextResult:
        model = req.model or cfg.text_model or self.info.default_text_model
        if not model:
            raise ProviderNotConfigured(self.info.name, "no model selected")
        messages: list[dict[str, Any]] = []
        if req.system:
            messages.append({"role": "system", "content": req.system})
        user: dict[str, Any] = {"role": "user", "content": req.prompt}
        if req.images:
            user["images"] = [base64.b64encode(i).decode() for i in req.images[:4]]
        messages.append(user)
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": req.temperature, "num_predict": req.max_tokens, "num_ctx": 8192},
        }
        if req.json_mode:
            body["format"] = "json"
        t0 = time.perf_counter()
        data = request_json(
            self.info.name, "POST", f"{self._base(cfg)}/api/chat", json_body=body,
            timeout=httpx.Timeout(connect=5.0, read=600.0, write=30.0, pool=5.0),  # CPU inference is slow
        )
        try:
            text = data["message"]["content"]
        except (KeyError, TypeError):
            raise ProviderBadResponse(self.info.name, "unexpected response shape") from None
        return TextResult(
            text=text, provider=self.info.name, model=model,
            input_tokens=data.get("prompt_eval_count"), output_tokens=data.get("eval_count"),
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )

    def list_models(self, cfg: ProviderRuntimeConfig) -> list[str]:
        data = request_json(self.info.name, "GET", f"{self._base(cfg)}/api/tags", timeout=5.0)
        return sorted(m["name"] for m in data.get("models", []) if m.get("name"))

    def embed(self, texts: list[str], cfg: ProviderRuntimeConfig, model: str = "nomic-embed-text") -> list[list[float]]:
        data = request_json(self.info.name, "POST", f"{self._base(cfg)}/api/embed",
                            json_body={"model": model, "input": texts}, timeout=120.0)
        return data.get("embeddings", [])
