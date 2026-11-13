"""Product video creator (slideshow composition — not generative video)."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Asset, Job, Product, Project
from app.db.session import get_db
from app.jobs.queue import enqueue
from app.routers.common import get_or_404, soft_delete
from app.routers.jobs import job_out
from app.services.assets import asset_url, thumb_url
from app.services.video import ASPECTS, TRANSITIONS

router = APIRouter(prefix="/videos", tags=["videos"])
LABEL = "Composed slideshow video (FFmpeg) — not AI-generated video"


class Scene(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:10])
    asset_id: str
    duration: float = Field(default=3.0, ge=1.0, le=15.0)
    text: str = Field(default="", max_length=200)
    text_position: str = Field(default="bottom", pattern="^(top|center|bottom)$")
    motion: str = Field(default="zoom_in", pattern="^(zoom_in|zoom_out|none)$")


class VideoIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    product_id: str | None = None
    aspect: str = Field(default="16:9")
    target_duration: float = Field(default=15, ge=3, le=120)


class VideoPatch(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    scenes: list[Scene] | None = Field(default=None, max_length=30)
    aspect: str | None = None
    transition: str | None = None
    transition_s: float | None = Field(default=None, ge=0.2, le=1.5)
    music_asset_id: str | None = None
    text_style: dict[str, Any] | None = None


def video_out(db: Session, p: Project) -> dict[str, Any]:
    data = p.data or {}
    scenes = []
    for s in data.get("scenes", []):
        a = db.get(Asset, s.get("asset_id", ""))
        scenes.append({**s, "thumb_url": thumb_url(a) if a else None, "missing": a is None or bool(a.deleted_at)})
    last = db.get(Asset, data.get("last_render_asset_id") or "") if data.get("last_render_asset_id") else None
    music = db.get(Asset, data.get("music_asset_id") or "") if data.get("music_asset_id") else None
    jobs = db.scalars(select(Job).where(Job.type == "video_render", Job.project_id == p.id)
                      .order_by(Job.created_at.desc()).limit(3)).all()
    total = sum(float(s.get("duration", 3)) for s in data.get("scenes", []))
    if len(scenes) > 1 and data.get("transition", "fade") != "none":
        total -= float(data.get("transition_s", 0.6)) * (len(scenes) - 1)
    return {"id": p.id, "name": p.name, "product_id": p.product_id, "aspect": data.get("aspect", "16:9"),
            "transition": data.get("transition", "fade"), "transition_s": data.get("transition_s", 0.6),
            "text_style": data.get("text_style") or {}, "scenes": scenes, "estimated_duration": round(max(0, total), 1),
            "music": {"asset_id": music.id, "filename": music.filename, "url": asset_url(music.id)} if music else None,
            "last_render": {"asset_id": last.id, "url": asset_url(last.id), "duration_s": last.duration_s,
                            "size_bytes": last.size_bytes} if last else None,
            "jobs": [job_out(j) for j in jobs], "label": LABEL, "updated_at": p.updated_at}


@router.get("/options")
def options() -> dict[str, Any]:
    return {"aspects": list(ASPECTS), "transitions": sorted(TRANSITIONS), "label": LABEL}


@router.get("")
def list_videos(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(Project).where(Project.kind == "video", Project.deleted_at.is_(None))
                      .order_by(Project.updated_at.desc())).all()
    return [{"id": p.id, "name": p.name, "aspect": (p.data or {}).get("aspect"),
             "scenes": len((p.data or {}).get("scenes", [])),
             "rendered": bool((p.data or {}).get("last_render_asset_id")), "updated_at": p.updated_at} for p in rows]


@router.post("", status_code=201)
def create_video(body: VideoIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    if body.aspect not in ASPECTS:
        raise HTTPException(422, f"aspect must be one of {list(ASPECTS)}")
    scenes: list[dict[str, Any]] = []
    product = get_or_404(db, Product, body.product_id) if body.product_id else None
    if product:
        # Auto storyboard: product photos first, then the product's generated images.
        ids = [pi.asset_id for pi in product.images if pi.role != "cutout"]
        gen = db.scalars(select(Asset.id).where(Asset.product_id == product.id, Asset.kind == "image",
                                                Asset.source == "generated", Asset.deleted_at.is_(None))
                         .order_by(Asset.created_at.desc()).limit(6)).all()
        ids += [g for g in gen if g not in ids]
        ids = ids[:8]
        texts = [product.name] + list(product.benefits or product.features or [])
        per = max(1.5, min(6.0, body.target_duration / max(1, len(ids))))
        for i, aid in enumerate(ids):
            scenes.append(Scene(asset_id=aid, duration=round(per, 1), text=(texts[i] if i < len(texts) else "")[:120],
                                motion="zoom_in" if i % 2 == 0 else "zoom_out").model_dump())
    p = Project(kind="video", name=body.name, product_id=body.product_id,
                brand_id=product.brand_id if product else None,
                data={"aspect": body.aspect, "transition": "fade", "transition_s": 0.6, "scenes": scenes,
                      "text_style": {"color": "#ffffff", "band_opacity": 0.45}})
    db.add(p)
    db.flush()
    return video_out(db, p)


@router.get("/{project_id}")
def get_video(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return video_out(db, get_or_404(db, Project, project_id))


@router.patch("/{project_id}")
def update_video(project_id: str, body: VideoPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, Project, project_id)
    data = dict(p.data or {})
    upd = body.model_dump(exclude_unset=True)
    if "name" in upd and upd["name"]:
        p.name = upd.pop("name")
    if upd.get("aspect") and upd["aspect"] not in ASPECTS:
        raise HTTPException(422, "invalid aspect")
    if upd.get("transition") and upd["transition"] not in TRANSITIONS:
        raise HTTPException(422, "invalid transition")
    if upd.get("music_asset_id"):
        m = get_or_404(db, Asset, upd["music_asset_id"])
        if m.kind != "audio":
            raise HTTPException(422, "music must be an audio file (MP3, WAV, M4A, OGG)")
    if "scenes" in upd and upd["scenes"] is not None:
        for s in upd["scenes"]:
            a = get_or_404(db, Asset, s["asset_id"])
            if a.kind != "image":
                raise HTTPException(422, "scenes must use images")
    data.update({k: v for k, v in upd.items() if k != "name"})
    p.data = data
    return video_out(db, p)


@router.post("/{project_id}/render", status_code=202)
def render(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, Project, project_id)
    if not (p.data or {}).get("scenes"):
        raise HTTPException(422, "add at least one scene")
    return job_out(enqueue(db, "video_render", {"project_id": p.id, "title": p.name}, project_id=p.id))


@router.delete("/{project_id}", status_code=204)
def delete_video(project_id: str, db: Session = Depends(get_db)) -> None:
    soft_delete(db, get_or_404(db, Project, project_id))
