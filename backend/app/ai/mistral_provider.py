from __future__ import annotations

from app.ai.base import ProviderInfo
from app.ai.openai_compat import OpenAICompatProvider


class MistralProvider(OpenAICompatProvider):
    """Adapter kept for completeness but marked NOT verified-free.

    As of 2026-11-13 Mistral's usage-limits documentation states API keys require billing
    activation (pay-as-you-go), contradicting older 'Experiment plan' announcements. Until
    a free tier is re-verified, the fallback manager will refuse to use this provider.
    """

    base_url = "https://api.mistral.ai/v1"
    info = ProviderInfo(
        name="mistral",
        label="Mistral (unverified — disabled)",
        kinds=("text",),
        local=False,
        free_tier_verified=False,
        verified_on="2026-11-13",
        source_url="https://docs.mistral.ai/admin/billing-usage/usage-limits",
        limits_note="Docs say API access needs billing activation. Not eligible under the free-only policy.",
        privacy_note="Hosted. Free-tier training policy could not be confirmed.",
        default_text_model="mistral-small-latest",
    )
