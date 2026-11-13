"""Cloudflare Workers AI REST API — text and image, within the daily free Neuron allocation.

Requires the account to be on Workers *Free* (no paid plan → no overage billing is possible).
If Cloudflare restricts a model to paid plans it returns 403 (code 5035); we surface that as
ProviderRefused and never retry it.
"""
from __future__ import annotations

import base64
import time
from typing import Any

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
from app.ai.http import request_json


class CloudflareProvider(Provider):
    info = ProviderInfo(
        name="cloudflare",
        label="Cloudflare Workers AI (free allocation)",
        kinds=("text", "image"),
        local=False,
        free_tier_verified=True,
        verified_on="2026-11-13",
        source_url="https://developers.cloudflare.com/workers-ai/platform/pricing/",
        limits_note="10,000 Neurons/day free on Workers Free (no overage possible without a paid plan). "
        "flux-1-schnell ≈ 4.8 Neurons per 512×512 tile / 9.6 per step. Some heavy models return 403 on Free.",
        privacy_note="Hosted on Cloudflare. Review Cloudflare's AI data policy before sending sensitive data.",
        license_note="FLUX.1 [schnell]: Apache-2.0 (outputs usable commercially).",
        default_text_model="@cf/meta/llama-3.1-8b-instruct",
        default_image_model="@cf/black-forest-labs/flux-1-schnell",
    )

    def is_configured(self, cfg: ProviderRuntimeConfig) -> bool:
        return bool(cfg.api_key and cfg.extra.get("account_id"))

    def _url(self, cfg: ProviderRuntimeConfig, model: str) -> tuple[str, dict[str, str]]:
        if not self.is_configured(cfg):
            raise ProviderNotConfigured(self.info.name, "account ID and API token required")
        acct = cfg.extra["account_id"]
        return (
            f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/run/{model}",
            {"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"},
        )

    def allowed_model(self, model: str) -> bool:
        return model.startswith("@cf/")

    def generate_text(self, req: TextRequest, cfg: ProviderRuntimeConfig) -> TextResult:
        model = req.model or cfg.text_model or self.info.default_text_model or ""
        url, headers = self._url(cfg, model)
        messages: list[dict[str, Any]] = []
        if req.system:
            messages.append({"role": "system", "content": req.system})
        messages.append({"role": "user", "content": req.prompt})
        t0 = time.perf_counter()
        data = request_json(self.info.name, "POST", url, headers=headers, secrets=[cfg.api_key],
                            json_body={"messages": messages, "max_tokens": req.max_tokens,
                                       "temperature": req.temperature})
        try:
            text = data["result"]["response"]
        except (KeyError, TypeError):
            raise ProviderBadResponse(self.info.name, "unexpected response shape") from None
        if not isinstance(text, str):  # some models return structured JSON already
            import json as _json
            text = _json.dumps(text)
        return TextResult(text=text, provider=self.info.name, model=model,
                          latency_ms=int((time.perf_counter() - t0) * 1000))

    def generate_image(self, req: ImageRequest, cfg: ProviderRuntimeConfig) -> ImageResult:
        model = req.model or cfg.image_model or self.info.default_image_model or ""
        url, headers = self._url(cfg, model)
        body: dict[str, Any] = {"prompt": req.prompt[:2048]}
        if "flux" in model:
            body["steps"] = min(8, req.steps or 4)
        else:
            body.update({"width": req.width, "height": req.height, "num_steps": min(20, req.steps or 8)})
            if req.negative_prompt:
                body["negative_prompt"] = req.negative_prompt
        if req.seed is not None:
            body["seed"] = req.seed
        t0 = time.perf_counter()
        if "flux" in model:
            data = request_json(self.info.name, "POST", url, headers=headers, json_body=body, secrets=[cfg.api_key])
            try:
                png = base64.b64decode(data["result"]["image"])
            except (KeyError, TypeError, ValueError):
                raise ProviderBadResponse(self.info.name, "no image in response") from None
        else:  # SDXL models return raw PNG bytes
            png = request_json(self.info.name, "POST", url, headers=headers, json_body=body,
                               secrets=[cfg.api_key], expect_binary=True)
        return ImageResult(image_png=png, provider=self.info.name, model=model, seed=req.seed,
                           latency_ms=int((time.perf_counter() - t0) * 1000))

    def list_models(self, cfg: ProviderRuntimeConfig) -> list[str]:
        if not self.is_configured(cfg):
            raise ProviderNotConfigured(self.info.name, "account ID and API token required")
        acct = cfg.extra["account_id"]
        data = request_json(
            self.info.name, "GET",
            f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/models/search?per_page=100",
            headers={"Authorization": f"Bearer {cfg.api_key}"}, secrets=[cfg.api_key], timeout=20.0,
        )
        return sorted(m.get("name", "") for m in data.get("result", []) if m.get("name"))
