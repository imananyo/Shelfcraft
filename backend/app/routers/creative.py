"""Image generation, spot edit, and reference-guided (Inspire) endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.models import Asset, CreativeSession, Product
from app.db.session import get_db
from app.jobs.queue import enqueue
from app.routers.common import get_or_404
from app.routers.jobs import job_out
from app.services.creative import CREATIVE_TYPES
from app.services.editing import OPERATIONS

router = APIRouter(tags=["creative"])

STYLES = ["minimal", "luxury", "natural", "vibrant", "editorial", "tech"]


@router.get("/creative/options")
def options() -> dict[str, Any]:
    return {"creative_types": {k: v["label"] for k, v in CREATIVE_TYPES.items()},
            "modes": {k: v["mode"] for k, v in CREATIVE_TYPES.items()}, "styles": STYLES,
            "edit_operations": OPERATIONS}


class GenerateIn(BaseModel):
    creative_type: str
    product_id: str | None = None
    brand_id: str | None = None
    width: int = Field(default=1024, ge=256, le=4096)
    height: int = Field(default=1024, ge=256, le=4096)
    style: str = Field(default="minimal", max_length=60)
    prompt: str | None = Field(default=None, max_length=2000)
    extra_prompt: str = Field(default="", max_length=600)
    provider: str | None = None
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)
    harmonize: bool = False
    count: int = Field(default=1, ge=1, le=4)
    template_id: str | None = None
    copy_: dict[str, Any] | None = Field(default=None, alias="copy")


@router.post("/creative/generate", status_code=202)
def generate(body: GenerateIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    if body.creative_type not in CREATIVE_TYPES:
        from fastapi import HTTPException

        raise HTTPException(422, f"unknown creative type {body.creative_type}")
    if body.product_id:
        get_or_404(db, Product, body.product_id)
    title = CREATIVE_TYPES[body.creative_type]["label"]
    session = CreativeSession(kind="image", title=title, params=body.model_dump(by_alias=True, exclude={"prompt"}))
    db.add(session)
    db.flush()
    jobs = []
    for i in range(body.count):
        payload = body.model_dump(by_alias=True)
        payload["seed"] = (body.seed + i) if body.seed is not None else None
        payload["session_id"] = session.id
        jobs.append(job_out(enqueue(db, "image_generate", payload, session_id=session.id)))
    return {"session_id": session.id, "jobs": jobs}


@router.get("/creative/sessions/{session_id}")
def get_session(session_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    from sqlalchemy import select

    from app.db.models import Job
    from app.routers.assets import asset_out

    s = get_or_404(db, CreativeSession, session_id)
    jobs = db.scalars(select(Job).where(Job.session_id == s.id).order_by(Job.created_at)).all()
    ids: list[str] = []
    for j in jobs:
        ids += (j.result or {}).get("asset_ids", [])
    assets = [asset_out(a) for a in (db.get(Asset, i) for i in ids) if a and not a.deleted_at]
    return {"id": s.id, "title": s.title, "params": s.params, "jobs": [job_out(j) for j in jobs], "assets": assets}


class MoreIn(BaseModel):
    prompt: str = Field(min_length=2, max_length=600)
    count: int = Field(default=2, ge=1, le=4)
    creative_type: str | None = None
    provider: str | None = None


@router.post("/creative/sessions/{session_id}/more", status_code=202)
def keep_prompting(session_id: str, body: MoreIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Keep prompting: more visuals in the same session, steered by a new instruction."""
    from fastapi import HTTPException

    s = get_or_404(db, CreativeSession, session_id)
    base = dict(s.params or {})
    if not base.get("creative_type"):
        raise HTTPException(422, "this session can't be continued (not an image session)")
    ctype = body.creative_type or base["creative_type"]
    if ctype not in CREATIVE_TYPES:
        raise HTTPException(422, f"unknown creative type {ctype}")
    history = list(base.get("follow_ups") or [])[-9:] + [body.prompt]
    s.params = {**base, "follow_ups": history}
    jobs = []
    for _ in range(body.count):
        payload = {**base, "creative_type": ctype, "extra_prompt": body.prompt, "seed": None, "session_id": s.id,
                   "count": 1, "provider": body.provider or base.get("provider")}
        payload.pop("follow_ups", None)
        jobs.append(job_out(enqueue(db, "image_generate", payload, session_id=s.id)))
    return {"session_id": s.id, "jobs": jobs}


class EditIn(BaseModel):
    asset_id: str
    operation: str
    mask: str | None = Field(default=None, max_length=30_000_000)  # PNG data URL
    prompt: str | None = Field(default=None, max_length=1000)
    background_mode: str | None = Field(default=None, pattern="^(color|asset|prompt)$")
    color: str | None = Field(default=None, pattern="^#[0-9a-fA-F]{6}$")
    background_asset_id: str | None = None
    width: int | None = Field(default=None, ge=64, le=4096)
    height: int | None = Field(default=None, ge=64, le=4096)
    engine: str | None = Field(default=None, pattern="^(lama|opencv)$")
    strength: float | None = Field(default=None, ge=0.1, le=1.0)
    factor: float | None = Field(default=None, ge=1.1, le=4.0)
    sharpen: float | None = Field(default=None, ge=0.5, le=3.0)
    saturation: float | None = Field(default=None, ge=0.0, le=2.0)
    brightness: float | None = Field(default=None, ge=0.5, le=1.5)
    denoise: bool | None = None
    provider: str | None = None


@router.post("/edits", status_code=202)
def start_edit(body: EditIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    from fastapi import HTTPException

    if body.operation not in OPERATIONS:
        raise HTTPException(422, f"unknown operation {body.operation}")
    get_or_404(db, Asset, body.asset_id)
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    return job_out(enqueue(db, "image_edit", payload))


# ---------------------------------------------------------------- Inspire (reference-guided)
@router.post("/inspire/analyze")
def inspire_analyze(body: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
    from app.services.inspire import analyze_reference

    a = get_or_404(db, Asset, str(body.get("asset_id", "")))
    tags = set(a.tags or [])
    tags.add("reference")
    a.tags = list(tags)
    return analyze_reference(db, a.id, use_vision=bool(body.get("use_vision", True)))


class InspireIn(BaseModel):
    reference_asset_id: str
    product_id: str
    brand_id: str | None = None
    width: int | None = Field(default=None, ge=256, le=4096)
    height: int | None = Field(default=None, ge=256, le=4096)
    provider: str | None = None
    seed: int | None = None
    copy_: dict[str, Any] | None = Field(default=None, alias="copy")


@router.post("/inspire/generate", status_code=202)
def inspire_generate(body: InspireIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    get_or_404(db, Asset, body.reference_asset_id)
    get_or_404(db, Product, body.product_id)
    return job_out(enqueue(db, "inspire_generate", body.model_dump(by_alias=True)))
