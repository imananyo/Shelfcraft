from __future__ import annotations

from typing import Any

from app.ai.base import ProviderInfo
from app.ai.model_health import AUTO
from app.ai.openai_compat import OpenAICompatProvider


class GroqProvider(OpenAICompatProvider):
    base_url = "https://api.groq.com/openai/v1"
    info = ProviderInfo(
        name="groq",
        label="Groq",
        kinds=("text",),
        local=False,
        free_tier_verified=True,
        verified_on="2026-11-13",
        source_url="https://console.groq.com/docs/rate-limits",
        limits_note="$0 Free plan exists; per-model RPM/RPD/TPM limits are shown in your Groq console "
        "(docs pages disagree on exact numbers). Batch API is paid — never used.",
        privacy_note="Hosted. Prompts are sent to Groq; review Groq's data policy before sending sensitive data.",
        # Groq removed llama-3.3-70b-versatile (Nov 2026); the best model the key can use is picked automatically.
        default_text_model=AUTO,
    )

    def extra_body(self, model: str) -> dict[str, Any]:
        # gpt-oss models "think" before answering; low effort keeps answers inside the token budget
        # (measured on a 12-review batch: 318 instead of 566 tokens, same result).
        return {"reasoning_effort": "low"} if "gpt-oss" in model else {}
