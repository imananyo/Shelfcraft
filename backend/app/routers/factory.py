"""Factory: bounded bulk creative generation over products × variants × creative types."""
from __future__ import annotations

import io
import zipfile
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Asset, ExportRecord, FactoryBatch, Job, Product
from app.db.session import get_db
from app.jobs import queue
from app.routers.common import get_or_404
from app.routers.jobs import job_out
from app.services.assets import safe_filename
from app.services.creative import CREATIVE_TYPES
from app.storage.local import get_storage

router = APIRouter(prefix="/factory", tags=["factory"])

SECONDS_ESTIMATE = {"cutout_white": 8, "composite": 45, "template": 20}


class FactoryIn(BaseModel):
    name: str = Field(default="Factory run", max_length=200)
    product_ids: list[str] = Field(min_length=1, max_length=100)
    include_variants: bool = False
    creative_types: list[str] = Field(min_length=1, max_length=10)
    brand_id: str | None = None
    template_id: str | None = None
    style: str = "minimal"
    prompt: str = Field(default="", max_length=600)
    width: int = Field(default=2000, ge=256, le=4096)
    height: int = Field(default=2000, ge=256, le=4096)
    provider: str | None = None
    dry_run: bool = False


def _plan(db: Session, body: FactoryIn) -> list[dict[str, Any]]:
    bad = [t for t in body.creative_types if t not in CREATIVE_TYPES]
    if bad:
        raise HTTPException(422, f"unknown creative types: {', '.join(bad)}")
    items = []
    for pid in body.product_ids:
        p = get_or_404(db, Product, pid)
        targets: list[tuple[str | None, dict[str, Any]]] = [(None, {})]
        if body.include_variants and p.variants:
            targets = [(v.name, v.attributes or {}) for v in p.variants]
        for vname, attrs in targets:
            for ct in body.creative_types:
                items.append({"product_id": p.id, "product_name": p.name, "variant_name": vname,
                              "variant_attributes": attrs, "creative_type": ct, "template_id": body.template_id,
                              "has_photo": any(pi.role != "cutout" for pi in p.images)})
    return items


@router.post("/preview")
def preview(body: FactoryIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    items = _plan(db, body)
    secs = sum(SECONDS_ESTIMATE[CREATIVE_TYPES[i["creative_type"]]["mode"]] for i in items)
    limit = get_settings().max_jobs_per_batch
    warnings = []
    if len(items) > limit:
        warnings.append(f"{len(items)} jobs exceeds the per-batch limit of {limit}. Reduce products or types.")
    missing = sorted({i["product_name"] for i in items if not i["has_photo"]})
    if missing:
        warnings.append("No photo for: " + ", ".join(missing[:10]) + " — images will be AI-imagined or fail for "
                        "white-background types.")
    return {"count": len(items), "items": items[:300], "estimated_minutes": round(secs / 60, 1), "warnings": warnings,
            "limit": limit}


@router.post("/batches", status_code=201)
def create_batch(body: FactoryIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    items = _plan(db, body)
    limit = get_settings().max_jobs_per_batch
    if len(items) > limit:
        raise HTTPException(422, f"{len(items)} jobs exceeds the per-batch limit of {limit}")
    active = db.scalar(select(func.count()).select_from(Job).where(Job.status.in_(("queued", "running")))) or 0
    if active + len(items) > limit * 2:
        raise HTTPException(429, f"{active} jobs already pending — wait for them to finish before queueing more")
    b = FactoryBatch(name=body.name, config=body.model_dump(exclude={"product_ids", "creative_types", "dry_run"}),
                     total=len(items))
    db.add(b)
    db.flush()
    for i in items:
        queue.enqueue(db, "factory_item", {**{k: v for k, v in i.items() if k != "has_photo"}, "batch_id": b.id},
                      batch_id=b.id, priority=-1)
    return batch_out(db, b)


def batch_out(db: Session, b: FactoryBatch) -> dict[str, Any]:
    jobs = db.scalars(select(Job).where(Job.batch_id == b.id).order_by(Job.created_at)).all()
    counts: dict[str, int] = {}
    for j in jobs:
        counts[j.status] = counts.get(j.status, 0) + 1
    done = counts.get("succeeded", 0) + counts.get("failed", 0) + counts.get("cancelled", 0)
    return {"id": b.id, "name": b.name, "config": b.config, "total": b.total, "counts": counts,
            "progress": round(done / b.total, 3) if b.total else 1.0, "created_at": b.created_at,
            "jobs": [job_out(j) for j in jobs]}


@router.get("/batches")
def list_batches(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    out = []
    for b in db.scalars(select(FactoryBatch).order_by(FactoryBatch.created_at.desc()).limit(50)):
        counts = dict(db.execute(select(Job.status, func.count()).where(Job.batch_id == b.id).group_by(Job.status)).all())
        out.append({"id": b.id, "name": b.name, "total": b.total, "counts": counts, "created_at": b.created_at})
    return out


@router.get("/batches/{batch_id}")
def get_batch(batch_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return batch_out(db, get_or_404(db, FactoryBatch, batch_id))


@router.post("/batches/{batch_id}/cancel")
def cancel_pending(batch_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    get_or_404(db, FactoryBatch, batch_id)
    n = 0
    for j in db.scalars(select(Job).where(Job.batch_id == batch_id, Job.status == "queued")):
        n += int(queue.cancel(db, j.id))
    return {"cancelled": n}


@router.post("/batches/{batch_id}/retry-failed")
def retry_failed(batch_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    get_or_404(db, FactoryBatch, batch_id)
    n = 0
    for j in db.scalars(select(Job).where(Job.batch_id == batch_id, Job.status.in_(("failed", "cancelled")))):
        n += int(queue.retry(db, j.id))
    return {"retried": n}


@router.get("/batches/{batch_id}/download")
def download(batch_id: str, db: Session = Depends(get_db)) -> StreamingResponse:
    b = get_or_404(db, FactoryBatch, batch_id)
    jobs = db.scalars(select(Job).where(Job.batch_id == b.id, Job.status == "succeeded")).all()
    if not jobs:
        raise HTTPException(422, "no finished items yet")
    buf = io.BytesIO()
    used: set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for j in jobs:
            for aid in (j.result or {}).get("asset_ids", []):
                a = db.get(Asset, aid)
                if a is None or a.deleted_at:
                    continue
                folder = safe_filename((j.payload or {}).get("product_name") or "product")
                name = f"{folder}/{safe_filename(a.title or a.filename)}"
                if not name.endswith(".png"):
                    name += ".png"
                while name in used:
                    name = name.replace(".png", "-1.png")
                used.add(name)
                z.write(get_storage().path(a.storage_key), name)
    db.add(ExportRecord(kind="zip", source_type="factory", source_id=b.id, params={"files": len(used)}))
    return StreamingResponse(iter([buf.getvalue()]), media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{safe_filename(b.name)}.zip"'})
