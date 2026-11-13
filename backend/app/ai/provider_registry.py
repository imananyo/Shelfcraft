"""Registry of provider adapters + resolution of their runtime config (DB row overlaid by env)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.ai.base import Provider, ProviderRuntimeConfig
from app.ai.cloudflare_provider import CloudflareProvider
from app.ai.gemini_provider import GeminiProvider
from app.ai.groq_provider import GroqProvider
from app.ai.local_diffusion_provider import LocalDiffusionProvider, diffusers_available
from app.ai.mistral_provider import MistralProvider
from app.ai.ollama_provider import OllamaProvider
from app.ai.openrouter_provider import OpenRouterProvider
from app.config import get_settings
from app.db.models import ProviderConfig

PROVIDERS: dict[str, Provider] = {
    p.info.name: p
    for p in (
        OllamaProvider(),
        GeminiProvider(),
        GroqProvider(),
        OpenRouterProvider(),
        CloudflareProvider(),
        MistralProvider(),
        LocalDiffusionProvider(),
    )
}


def get_provider(name: str) -> Provider:
    if name not in PROVIDERS:
        raise KeyError(f"unknown provider: {name}")
    return PROVIDERS[name]


def is_free_eligible(p: Provider) -> bool:
    """The single gate that keeps paid services out of every code path."""
    return p.info.local or p.info.free_tier_verified


def _env_key(name: str) -> tuple[str | None, dict[str, Any]]:
    s = get_settings()
    extra: dict[str, Any] = {}
    key = {
        "gemini": s.gemini_api_key,
        "groq": s.groq_api_key,
        "openrouter": s.openrouter_api_key,
        "mistral": s.mistral_api_key,
        "cloudflare": s.cloudflare_api_token,
    }.get(name)
    if name == "cloudflare" and s.cloudflare_account_id:
        extra["account_id"] = s.cloudflare_account_id
    if name == "ollama":
        extra["base_url"] = s.ollama_base_url
    return key, extra


def ensure_rows(db: Session) -> None:
    """Create a config row per provider on first run with safe defaults."""
    existing = {r.name for r in db.query(ProviderConfig).all()}
    for name, p in PROVIDERS.items():
        if name in existing:
            continue
        key, _ = _env_key(name)
        enabled = (
            name == "ollama"
            or (name == "local_diffusion" and diffusers_available())
            or (bool(key) and is_free_eligible(p))
        )
        db.add(ProviderConfig(name=name, enabled=enabled))
    db.flush()


def runtime_config(db: Session, name: str) -> ProviderRuntimeConfig:
    row = db.get(ProviderConfig, name)
    env_key, env_extra = _env_key(name)
    extra = {**(row.extra if row and row.extra else {}), **{k: v for k, v in env_extra.items() if v}}
    return ProviderRuntimeConfig(
        enabled=bool(row and row.enabled),
        api_key=env_key or (row.api_key if row else None),
        extra=extra,
        text_model=row.text_model if row else None,
        image_model=row.image_model if row else None,
    )


def provider_status(db: Session, name: str) -> dict[str, Any]:
    """Client-safe status. Never includes the key itself."""
    p = get_provider(name)
    row = db.get(ProviderConfig, name)
    cfg = runtime_config(db, name)
    now = datetime.now(timezone.utc)

    def _aware(dt: datetime | None) -> datetime | None:
        return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt

    rl = _aware(row.rate_limited_until) if row else None
    co = _aware(row.circuit_open_until) if row else None
    configured = p.is_configured(cfg)
    if not is_free_eligible(p):
        state = "ineligible"
    elif not cfg.enabled:
        state = "disabled"
    elif not configured:
        state = "not_configured"
    elif rl and rl > now:
        state = "rate_limited"
    elif co and co > now:
        state = "unavailable"
    else:
        state = "available"
    i = p.info
    env_key, _ = _env_key(name)
    return {
        "name": name,
        "label": i.label,
        "kinds": list(i.kinds),
        "local": i.local,
        "free_tier_verified": i.free_tier_verified,
        "verified_on": i.verified_on,
        "source_url": i.source_url,
        "limits_note": i.limits_note,
        "privacy_note": i.privacy_note,
        "license_note": i.license_note,
        "requires_key": i.requires_key,
        "vision": i.vision,
        "enabled": cfg.enabled,
        "has_key": bool(cfg.api_key),
        "key_source": "env" if env_key else ("settings" if row and row.api_key else None),
        "extra": {k: v for k, v in cfg.extra.items() if k in ("account_id", "base_url")},
        "configured": configured,
        "state": state,
        "text_model": cfg.text_model or i.default_text_model,
        "image_model": cfg.image_model or i.default_image_model,
        "default_text_model": i.default_text_model,
        "default_image_model": i.default_image_model,
        "last_success_at": row.last_success_at if row else None,
        "last_failure_at": row.last_failure_at if row else None,
        "last_error": row.last_error if row else None,
        "rate_limited_until": rl,
        "circuit_open_until": co,
    }
