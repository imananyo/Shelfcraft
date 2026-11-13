from __future__ import annotations

from app.ai.base import ProviderInfo, ProviderRuntimeConfig
from app.ai.http import request_json
from app.ai.openai_compat import OpenAICompatProvider


class OpenRouterProvider(OpenAICompatProvider):
    """Only model IDs ending in ':free' are accepted — paid models are rejected before any call."""

    base_url = "https://openrouter.ai/api/v1"
    supports_json_mode = False  # not uniformly supported by free backends; we parse loosely
    info = ProviderInfo(
        name="openrouter",
        label="OpenRouter (free models only)",
        kinds=("text",),
        local=False,
        free_tier_verified=True,
        verified_on="2026-11-13",
        source_url="https://openrouter.ai/pricing",
        limits_note="':free' models: 20 req/min and 50 req/day (1,000/day only after buying credits — "
        "Shelfcraft never buys credits). Failed requests count toward the cap.",
        privacy_note="Hosted. Some free endpoints may log or train on prompts — check each model's provider page.",
        default_text_model="meta-llama/llama-3.3-70b-instruct:free",
    )

    def allowed_model(self, model: str) -> bool:
        return model.endswith(":free")

    def _headers(self, cfg: ProviderRuntimeConfig) -> dict[str, str]:
        h = super()._headers(cfg)
        h["X-Title"] = "Shelfcraft (local)"
        return h

    def list_models(self, cfg: ProviderRuntimeConfig) -> list[str]:
        data = request_json(self.info.name, "GET", f"{self.base_url}/models", timeout=20.0)
        out = []
        for m in data.get("data", []):
            pricing = m.get("pricing") or {}
            if m.get("id", "").endswith(":free") and str(pricing.get("prompt", "1")) in ("0", "0.0"):
                out.append(m["id"])
        return sorted(out)
