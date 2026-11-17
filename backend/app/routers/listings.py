"""Product intelligence + listing builder."""
from __future__ import annotations

import csv
import io
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Brand, CreativeSession, Job, Product, ProductResearch, Project
from app.db.session import get_db
from app.jobs.queue import enqueue
from app.routers.common import get_or_404, soft_delete
from app.routers.jobs import job_out
from app.services.copywriting import normalize_copy
from app.services.marketplaces import MARKETPLACES, SIZE_PRESETS, validate_copy

router = APIRouter(tags=["listings"])


# ---------------------------------------------------------------- research
class ResearchIn(BaseModel):
    reviews: str = Field(default="", max_length=20000)
    competitors: str = Field(default="", max_length=10000)
    notes: str = Field(default="", max_length=2000)
    provider: str | None = None


@router.post("/products/{product_id}/research", status_code=202)
def start_research(product_id: str, body: ResearchIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    get_or_404(db, Product, product_id)
    job = enqueue(db, "product_research", {"product_id": product_id, **body.model_dump()})
    return job_out(job)


@router.get("/products/{product_id}/research")
def list_research(product_id: str, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(ProductResearch).where(ProductResearch.product_id == product_id,
                                                    ProductResearch.kind.notin_(("reviews", "category")))
                      .order_by(ProductResearch.created_at.desc()).limit(10)).all()
    return [{"id": r.id, "result": r.result, "inputs": r.inputs, "provider": r.provider, "model": r.model,
             "created_at": r.created_at} for r in rows]


# ---------------------------------------------------------------- listing projects
@router.get("/marketplaces")
def marketplaces() -> dict[str, Any]:
    return {"marketplaces": MARKETPLACES, "size_presets": SIZE_PRESETS}


class ListingIn(BaseModel):
    product_id: str
    brand_id: str | None = None
    marketplace: str = Field(default="amazon", pattern="^(amazon|amazon_mobile|shopify|walmart|tiktok)$")
    country: str = Field(default="US", max_length=8)
    language: str = Field(default="en", max_length=16)
    audience: str | None = Field(default=None, max_length=1000)
    tone: str | None = Field(default=None, max_length=200)
    keywords: str | None = Field(default=None, max_length=1000)
    creative_preferences: str | None = Field(default=None, max_length=1000)
    provider: str | None = None
    generate: bool = True


def listing_out(db: Session, p: Project) -> dict[str, Any]:
    from app.db.models import Asset
    from app.services.assets import asset_url, thumb_url

    data = p.data or {}
    product = db.get(Product, p.product_id) if p.product_id else None
    jobs = db.scalars(select(Job).where(Job.project_id == p.id).order_by(Job.created_at.desc()).limit(5)).all()
    images = []
    for item in data.get("images") or []:
        for aid in item.get("asset_ids", []):
            a = db.get(Asset, aid)
            if a and not a.deleted_at:
                images.append({"slot": item.get("slot"), "asset_id": a.id, "url": asset_url(a.id), "thumb_url": thumb_url(a),
                               "document_id": item.get("document_id"), "provider": a.provider, "model": a.model,
                               "is_ai_generated": a.is_ai_generated, "title": a.title})
    return {
        "id": p.id, "name": p.name, "product_id": p.product_id, "product_name": product.name if product else None,
        "brand_id": p.brand_id, "marketplace": data.get("marketplace", "amazon"), "options": data.get("options", {}),
        "copy": normalize_copy(data.get("copy")), "warnings": data.get("warnings", []), "provenance": data.get("provenance"),
        "versions": len(data.get("versions") or []), "images": images, "image_errors": data.get("image_errors", []),
        "limits": MARKETPLACES.get(data.get("marketplace", "amazon"), MARKETPLACES["amazon"])["fields"],
        "jobs": [job_out(j) for j in jobs], "updated_at": p.updated_at, "created_at": p.created_at,
    }


@router.get("/listings")
def list_listings(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(Project).where(Project.kind == "listing", Project.deleted_at.is_(None))
                      .order_by(Project.updated_at.desc())).all()
    out = []
    for p in rows:
        product = db.get(Product, p.product_id) if p.product_id else None
        out.append({"id": p.id, "name": p.name, "marketplace": (p.data or {}).get("marketplace"),
                    "product_name": product.name if product else None, "has_copy": bool((p.data or {}).get("copy")),
                    "image_count": sum(len(i.get("asset_ids", [])) for i in (p.data or {}).get("images") or []),
                    "updated_at": p.updated_at})
    return out


@router.post("/listings", status_code=201)
def create_listing(body: ListingIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    product = get_or_404(db, Product, body.product_id)
    brand_id = body.brand_id or product.brand_id
    if brand_id:
        get_or_404(db, Brand, brand_id)
    mk = MARKETPLACES[body.marketplace]["label"]
    p = Project(kind="listing", name=f"{product.name} — {mk}"[:200], product_id=product.id, brand_id=brand_id,
                data={"marketplace": body.marketplace, "options": body.model_dump(
                    include={"country", "language", "audience", "tone", "keywords", "creative_preferences"})})
    db.add(p)
    db.flush()
    db.add(CreativeSession(project_id=p.id, kind="listing", title=p.name, params={"marketplace": body.marketplace}))
    if body.generate:
        enqueue(db, "listing_copy", {"project_id": p.id, "provider": body.provider}, project_id=p.id)
    return listing_out(db, p)


@router.get("/listings/{project_id}")
def get_listing(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return listing_out(db, get_or_404(db, Project, project_id))


class CopyPatch(BaseModel):
    copy_: dict[str, Any] = Field(alias="copy")
    options: dict[str, Any] | None = None
    save_version: bool = False


@router.put("/listings/{project_id}/copy")
def save_copy(project_id: str, body: CopyPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, Project, project_id)
    data = dict(p.data or {})
    if body.save_version and data.get("copy"):
        data["versions"] = (list(data.get("versions") or []) + [{"copy": data["copy"], "provenance": data.get("provenance")}])[-20:]
    data["copy"] = body.copy_
    if body.options is not None:
        data["options"] = {**data.get("options", {}), **body.options}
    data["warnings"] = validate_copy(data.get("marketplace", "amazon"), body.copy_)
    data["provenance"] = {**(data.get("provenance") or {}), "edited_by_user": True}
    p.data = data
    return listing_out(db, p)


class RegenIn(BaseModel):
    field: str | None = Field(default=None, pattern="^(title|bullets|description|keywords|image_strategy)$")
    instruction: str | None = Field(default=None, max_length=500)
    provider: str | None = None


@router.post("/listings/{project_id}/generate", status_code=202)
def regenerate(project_id: str, body: RegenIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, Project, project_id)
    if body.instruction:
        data = dict(p.data or {})
        data["options"] = {**data.get("options", {}), "instruction": body.instruction}
        p.data = data
    job = enqueue(db, "listing_copy", {"project_id": p.id, "field": body.field, "provider": body.provider},
                  project_id=p.id)
    return job_out(job)


class ImagesIn(BaseModel):
    slots: list[str] | None = None
    style: str = "minimal"
    provider: str | None = None


@router.post("/listings/{project_id}/images", status_code=202)
def generate_images(project_id: str, body: ImagesIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, Project, project_id)
    job = enqueue(db, "listing_images", {"project_id": p.id, **body.model_dump()}, project_id=p.id)
    return job_out(job)


class MoreImagesIn(BaseModel):
    prompt: str = Field(default="", max_length=600)
    creative_type: str = Field(default="lifestyle", max_length=40)
    count: int = Field(default=2, ge=1, le=4)
    style: str = Field(default="minimal", max_length=40)
    provider: str | None = None


@router.post("/listings/{project_id}/images/more", status_code=202)
def more_images(project_id: str, body: MoreImagesIn, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Add more visuals to the same listing session (Pixii's "Add more visuals")."""
    from app.services.creative import CREATIVE_TYPES

    p = get_or_404(db, Project, project_id)
    if body.creative_type not in CREATIVE_TYPES:
        raise HTTPException(422, f"unknown creative type {body.creative_type}")
    return [job_out(enqueue(db, "listing_more_images", {"project_id": p.id, **body.model_dump(exclude={"count"})}, project_id=p.id))
            for _ in range(body.count)]


class RemoveImagesIn(BaseModel):
    asset_ids: list[str] = Field(min_length=1, max_length=100)


@router.post("/listings/{project_id}/images/remove")
def remove_images(project_id: str, body: RemoveImagesIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Remove visuals from the set (the files are moved to the library's trash, not destroyed)."""
    from app.db.models import Asset

    p = get_or_404(db, Project, project_id)
    drop = set(body.asset_ids)
    data = dict(p.data or {})
    kept = []
    for item in data.get("images") or []:
        ids = [a for a in item.get("asset_ids", []) if a not in drop]
        if ids:
            kept.append({**item, "asset_ids": ids})
    data["images"] = kept
    p.data = data
    for aid in drop:
        a = db.get(Asset, aid)
        if a and a.project_id == p.id:
            soft_delete(db, a)
    return listing_out(db, p)


@router.post("/listings/{project_id}/restore/{index}")
def restore_version(project_id: str, index: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, Project, project_id)
    data = dict(p.data or {})
    versions = list(data.get("versions") or [])
    if not 0 <= index < len(versions):
        raise HTTPException(404, "version not found")
    current = data.get("copy")
    data["copy"] = versions[index]["copy"]
    if current:
        versions.append({"copy": current, "provenance": data.get("provenance")})
    data["versions"] = versions[-20:]
    data["warnings"] = validate_copy(data.get("marketplace", "amazon"), data["copy"])
    p.data = data
    return listing_out(db, p)


@router.get("/listings/{project_id}/versions")
def versions(project_id: str, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    p = get_or_404(db, Project, project_id)
    return [{"index": i, "title": (v.get("copy") or {}).get("title"), "provenance": v.get("provenance")}
            for i, v in enumerate((p.data or {}).get("versions") or [])]


@router.get("/listings/{project_id}/export")
def export_listing(project_id: str, format: str = Query("txt", pattern="^(txt|json|csv)$"),
                   db: Session = Depends(get_db)) -> Response:
    p = get_or_404(db, Project, project_id)
    c = normalize_copy((p.data or {}).get("copy")) or {}
    name ="".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in p.name)[:80]
    if format == "json":
        body, mime = json.dumps({"marketplace": (p.data or {}).get("marketplace"), **c}, indent=2, ensure_ascii=False), "application/json"
    elif format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["field", "value"])
        w.writerow(["title", c.get("title", "")])
        for i, b in enumerate(c.get("bullets") or [], 1):
            w.writerow([f"bullet_{i}", b])
        w.writerow(["description", c.get("description", "")])
        w.writerow(["search_terms", c.get("search_terms", "")])
        w.writerow(["keywords", ", ".join(c.get("keywords") or [])])
        body, mime = buf.getvalue(), "text/csv"
    else:
        lines = [f"TITLE\n{c.get('title', '')}\n", "BULLETS"]
        lines += [f"• {b}" for b in c.get("bullets") or []]
        lines += ["", "DESCRIPTION", c.get("description", ""), "", "SEARCH TERMS", c.get("search_terms", ""),
                  "", "KEYWORDS", ", ".join(c.get("keywords") or [])]
        body, mime = "\n".join(lines), "text/plain"
    return Response(body, media_type=f"{mime}; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}.{format}"'})


@router.delete("/listings/{project_id}", status_code=204)
def delete_listing(project_id: str, db: Session = Depends(get_db)) -> None:
    soft_delete(db, get_or_404(db, Project, project_id))
