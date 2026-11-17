"""AI provider management and user settings."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai.base import ProviderError
from app.ai.provider_registry import PROVIDERS, get_provider, is_usable, provider_status, runtime_config
from app.ai.usage_tracker import usage_summary
from app.db.models import ProviderConfig, UserSettings
from app.db.session import get_db

router = APIRouter(tags=["providers"])


@router.get("/providers")
def list_providers(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [provider_status(db, n) for n in PROVIDERS]


class ProviderPatch(BaseModel):
    enabled: bool | None = None
    api_key: str | None = Field(default=None, max_length=500)  # "" clears the stored key
    account_id: str | None = Field(default=None, max_length=100)
    base_url: str | None = Field(default=None, max_length=200)
    text_model: str | None = Field(default=None, max_length=160)
    image_model: str | None = Field(default=None, max_length=160)


@router.patch("/providers/{name}")
def update_provider(name: str, body: ProviderPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    if name not in PROVIDERS:
        raise HTTPException(404, "unknown provider")
    p = get_provider(name)
    row = db.get(ProviderConfig, name) or ProviderConfig(name=name)
    db.add(row)
    data = body.model_dump(exclude_unset=True)
    if data.get("enabled") and not is_usable(db, p):
        if p.info.paid:
            raise HTTPException(422, f"{p.info.label} costs money per call. Turn on \"Allow paid providers\" in "
                                     "Settings → Providers first.")
        raise HTTPException(422, f"{p.info.label} cannot be enabled: its free tier is not verified "
                                 f"(checked {p.info.verified_on}). Shelfcraft only uses free or local providers.")
    if "enabled" in data:
        row.enabled = bool(data["enabled"])
    if "api_key" in data:
        row.api_key = (data["api_key"] or "").strip() or None
    extra = dict(row.extra or {})
    for k in ("account_id", "base_url"):
        if k in data:
            extra[k] = (data[k] or "").strip() or None
    row.extra = {k: v for k, v in extra.items() if v}
    for k in ("text_model", "image_model"):
        if k in data:
            model = (data[k] or "").strip() or None
            if model and not p.allowed_model(model):
                raise HTTPException(422, f"model '{model}' is not on {p.info.label}'s free allow-list")
            setattr(row, k, model)
    row.consecutive_failures, row.circuit_open_until, row.rate_limited_until = 0, None, None
    db.flush()
    return provider_status(db, name)


@router.post("/providers/{name}/test")
def test_provider(name: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Connectivity check that lists models — does not run a generation (saves free quota)."""
    if name not in PROVIDERS:
        raise HTTPException(404, "unknown provider")
    p = get_provider(name)
    cfg = runtime_config(db, name)
    if not p.is_configured(cfg):
        return {"ok": False, "detail": "Not configured — add the required key/settings first.", "models": []}
    try:
        models = p.list_models(cfg)
        return {"ok": True, "detail": f"Connected. {len(models)} eligible model(s).", "models": models[:100]}
    except ProviderError as e:
        return {"ok": False, "detail": e.message, "models": []}


@router.get("/usage")
def get_usage(days: int = 30, db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"days": days, "by_provider": usage_summary(db, days)}


class SettingsPatch(BaseModel):
    theme: str | None = Field(default=None, pattern="^(light|dark|system)$")
    default_text_provider: str | None = None
    default_image_provider: str | None = None
    fallback_order: list[str] | None = None
    generation_defaults: dict[str, Any] | None = None
    privacy_ack_hosted: bool | None = None
    display_name: str | None = Field(default=None, max_length=120)


def settings_out(s: UserSettings) -> dict[str, Any]:
    return {
        "theme": s.theme, "active_brand_id": s.active_brand_id, "default_text_provider": s.default_text_provider,
        "default_image_provider": s.default_image_provider, "fallback_order": s.fallback_order or [],
        "generation_defaults": s.generation_defaults or {}, "privacy_ack_hosted": s.privacy_ack_hosted,
        "onboarding": s.onboarding or {}, "display_name": s.user.display_name if s.user else "You",
    }


@router.get("/settings")
def get_settings_route(db: Session = Depends(get_db)) -> dict[str, Any]:
    s = db.query(UserSettings).first()
    assert s is not None
    return settings_out(s)


@router.patch("/settings")
def patch_settings(body: SettingsPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = db.query(UserSettings).first()
    assert s is not None
    data = body.model_dump(exclude_unset=True)
    for key in ("default_text_provider", "default_image_provider"):
        if key in data and data[key] not in PROVIDERS and data[key] != "local_composite":
            raise HTTPException(422, f"unknown provider {data[key]}")
    if "fallback_order" in data:
        data["fallback_order"] = [n for n in data["fallback_order"] if n in PROVIDERS]
    if "display_name" in data:
        s.user.display_name = data.pop("display_name") or "You"
    for k, v in data.items():
        setattr(s, k, v)
    return settings_out(s)
