"""Scale, Labs, Playbooks, Ads, Grader and media tools."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.base import NoProviderAvailable
from app.config import get_settings
from app.db.models import Asset, Brand, EditorDocument, FactoryBatch, Playbook, Product, Project
from app.db.session import get_db
from app.jobs.queue import enqueue
from app.routers.common import get_or_404, soft_delete
from app.routers.jobs import job_out
from app.services.assets import create_asset_from_upload, load_image, thumb_url
from app.services.documents import document_json

router = APIRouter(tags=["growth"])


# ---------------------------------------------------------------- Listing Grader
class GradeIn(BaseModel):
    listing_id: str | None = None
    marketplace: str = "amazon"
    title: str = Field(default="", max_length=1000)
    bullets: list[str] = Field(default_factory=list, max_length=10)
    description: str = Field(default="", max_length=20000)
    search_terms: str = Field(default="", max_length=2000)
    keywords: list[str] = Field(default_factory=list, max_length=50)
    brand: str | None = Field(default=None, max_length=120)
    asset_ids: list[str] = Field(default_factory=list, max_length=12)
    has_aplus: bool = False
    ai_review: bool = False


def grade_payload(db: Session, body: GradeIn) -> dict[str, Any]:
    from app.services.grader import ai_critique, grade

    listing = body.model_dump(include={"title", "bullets", "description", "search_terms", "keywords"})
    asset_ids, marketplace, brand_name, has_aplus = list(body.asset_ids), body.marketplace, body.brand, body.has_aplus
    if body.listing_id:
        proj = get_or_404(db, Project, body.listing_id)
        data = proj.data or {}
        listing = {**listing, **(data.get("copy") or {})}
        marketplace = data.get("marketplace", marketplace)
        brand = db.get(Brand, proj.brand_id) if proj.brand_id else None
        brand_name = brand_name or (brand.name if brand else None)
        if not asset_ids:
            for item in data.get("images") or []:
                asset_ids += item.get("asset_ids", [])[:1]
        if not has_aplus and proj.product_id:
            has_aplus = db.scalar(select(Project.id).where(Project.kind == "aplus", Project.product_id == proj.product_id,
                                                           Project.deleted_at.is_(None)).limit(1)) is not None
    images = []
    for aid in asset_ids[:12]:
        a = db.get(Asset, aid)
        if a and a.kind == "image" and not a.deleted_at:
            images.append(load_image(a))
    result = grade(listing, images, marketplace=marketplace, brand=brand_name, has_aplus=has_aplus)
    if body.ai_review:
        try:
            result["ai_review"] = ai_critique(listing, marketplace)
        except (NoProviderAvailable, ValueError) as e:
            result["ai_review"] = {"error": str(e)}
    return result


@router.post("/grader")
def grade_listing(body: GradeIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    return grade_payload(db, body)


# ---------------------------------------------------------------- Translate
class TranslateIn(BaseModel):
    language: str = Field(min_length=2, max_length=10)
    country: str = Field(default="US", max_length=8)
    translate_images: bool = True
    provider: str | None = None


@router.post("/listings/{project_id}/translate", status_code=202)
def translate(project_id: str, body: TranslateIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, Project, project_id)
    if not (p.data or {}).get("copy"):
        raise HTTPException(422, "generate the listing copy first")
    return job_out(enqueue(db, "listing_translate", {"project_id": p.id, **body.model_dump()}, project_id=p.id))


@router.get("/languages")
def languages() -> dict[str, str]:
    from app.services.growth import LANGUAGES

    return LANGUAGES


# ---------------------------------------------------------------- Bulk listing copy (Labs → Title & Bullets bulk run)
class BulkCopyIn(BaseModel):
    product_ids: list[str] = Field(min_length=1, max_length=100)
    marketplace: str = "amazon"
    language: str = "en"
    country: str = "US"
    brand_id: str | None = None
    provider: str | None = None


@router.post("/listings/bulk", status_code=201)
def bulk_copy(body: BulkCopyIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    if len(body.product_ids) > get_settings().max_jobs_per_batch:
        raise HTTPException(422, "too many products in one run")
    b = FactoryBatch(name=f"Bulk listing copy ({len(body.product_ids)})", total=len(body.product_ids),
                     config={"kind": "bulk_copy", **body.model_dump(exclude={"product_ids"})})
    db.add(b)
    db.flush()
    for pid in body.product_ids:
        p = get_or_404(db, Product, pid)
        enqueue(db, "bulk_listing_copy", {**body.model_dump(exclude={"product_ids"}), "product_id": pid, "product_name": p.name,
                                          "creative_type": "listing_copy", "batch_id": b.id}, batch_id=b.id)
    return {"batch_id": b.id, "total": b.total}


# ---------------------------------------------------------------- Packaging ideas
class PackagingIn(BaseModel):
    product_id: str
    count: int = Field(default=15, ge=3, le=15)
    notes: str = Field(default="", max_length=1000)
    provider: str | None = None


@router.post("/labs/packaging", status_code=202)
def packaging(body: PackagingIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    get_or_404(db, Product, body.product_id)
    return job_out(enqueue(db, "packaging_ideas", body.model_dump()))


@router.get("/labs/packaging")
def packaging_list(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(Project).where(Project.kind == "packaging", Project.deleted_at.is_(None)).order_by(Project.created_at.desc())).all()
    return [{"id": p.id, "name": p.name, "count": len((p.data or {}).get("concepts", [])), "created_at": p.created_at} for p in rows]


@router.get("/labs/packaging/{project_id}")
def packaging_get(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, Project, project_id)
    renders = {k: thumb_url(db.get(Asset, v)) for k, v in ((p.data or {}).get("renders") or {}).items() if db.get(Asset, v)}
    return {"id": p.id, "name": p.name, "product_id": p.product_id, **(p.data or {}), "render_urls": renders}


@router.post("/labs/packaging/{project_id}/render/{index}", status_code=202)
def packaging_render(project_id: str, index: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, Project, project_id)
    if not 0 <= index < len((p.data or {}).get("concepts", [])):
        raise HTTPException(404, "concept not found")
    return job_out(enqueue(db, "packaging_render", {"project_id": p.id, "index": index}, project_id=p.id))


# ---------------------------------------------------------------- Amazon Ads studio
class AdsIn(BaseModel):
    product_id: str
    format: str = Field(default="sb_image", pattern="^(sb_image|sb_video|sp_video|social_feed|story_ad)$")
    count: int = Field(default=6, ge=2, le=12)
    personas: list[str] | None = None
    goal: str = Field(default="conversions", max_length=60)
    provider: str | None = None


@router.get("/ads/formats")
def ad_formats() -> dict[str, Any]:
    from app.services.growth import AD_FORMATS

    return AD_FORMATS


@router.post("/ads", status_code=201)
def ads_create(body: AdsIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    product = get_or_404(db, Product, body.product_id)
    p = Project(kind="ads", name=f"Ads — {product.name}"[:200], product_id=product.id, brand_id=product.brand_id,
                data={"format": body.format, "goal": body.goal, "concepts": [], "renders": {}})
    db.add(p)
    db.flush()
    job = enqueue(db, "ad_concepts", {**body.model_dump(), "project_id": p.id}, project_id=p.id)
    return {"id": p.id, "job": job_out(job)}


@router.get("/ads")
def ads_list(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(Project).where(Project.kind == "ads", Project.deleted_at.is_(None)).order_by(Project.updated_at.desc())).all()
    return [{"id": p.id, "name": p.name, "format": (p.data or {}).get("format"), "concepts": len((p.data or {}).get("concepts", [])),
             "updated_at": p.updated_at} for p in rows]


@router.get("/ads/{project_id}")
def ads_get(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    from app.db.models import Job

    p = get_or_404(db, Project, project_id)
    renders = {}
    for k, v in ((p.data or {}).get("renders") or {}).items():
        a = db.get(Asset, (v.get("asset_ids") or [None])[0])
        if a:
            renders[k] = {"asset_id": a.id, "thumb_url": thumb_url(a), "document_id": v.get("document_id"), "provider": a.provider, "model": a.model}
    jobs = db.scalars(select(Job).where(Job.project_id == p.id).order_by(Job.created_at.desc()).limit(20)).all()
    return {"id": p.id, "name": p.name, "product_id": p.product_id, **(p.data or {}), "renders": renders, "jobs": [job_out(j) for j in jobs]}


@router.post("/ads/{project_id}/render", status_code=202)
def ads_render(project_id: str, body: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, Project, project_id)
    idx = [int(i) for i in body.get("indices") or range(len((p.data or {}).get("concepts", [])))]
    fmt = (p.data or {}).get("format", "sb_image")
    from app.services.growth import AD_FORMATS

    if AD_FORMATS.get(fmt, {}).get("kind") == "video":
        # Video formats become a storyboard per concept (text overlays = headline, subheadline, CTA).
        from app.routers.videos import VideoIn, create_video

        out = []
        for i in idx:
            c = (p.data or {})["concepts"][i]
            v = create_video(VideoIn(name=f"{p.name} — {c.get('headline', 'concept')}"[:200], product_id=p.product_id,
                                     aspect=AD_FORMATS[fmt].get("aspect", "16:9"), target_duration=AD_FORMATS[fmt].get("duration", 10)), db)
            vp = db.get(Project, v["id"])
            texts = [c.get("headline", ""), c.get("subheadline", ""), c.get("cta", "")]
            vp.data = {**vp.data, "scenes": [{**s, "text": texts[j] if j < len(texts) else ""} for j, s in enumerate(vp.data.get("scenes", []))]}
            out.append(job_out(enqueue(db, "video_render", {"project_id": vp.id, "title": vp.name}, project_id=vp.id)))
        return {"jobs": out}
    return {"jobs": [job_out(enqueue(db, "ad_render", {"project_id": p.id, "index": i, "style": body.get("style", "vibrant")}, project_id=p.id))
                     for i in idx]}


# ---------------------------------------------------------------- Playbooks
class PlaybookIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    category: str = Field(default="custom", max_length=40)
    steps: list[dict[str, Any]] = Field(min_length=1, max_length=20)
    settings: dict[str, Any] = Field(default_factory=dict)


def playbook_out(p: Playbook) -> dict[str, Any]:
    return {"id": p.id, "name": p.name, "description": p.description, "category": p.category, "steps": p.steps or [],
            "settings": p.settings or {}, "is_template": p.is_template, "updated_at": p.updated_at}


@router.get("/playbooks")
def playbooks(templates: bool = False, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    stmt = select(Playbook).where(Playbook.deleted_at.is_(None), Playbook.is_template.is_(templates))
    return [playbook_out(p) for p in db.scalars(stmt.order_by(Playbook.updated_at.desc()))]


@router.post("/playbooks", status_code=201)
def playbook_create(body: PlaybookIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    from app.services.playbooks import validate_steps

    try:
        validate_steps(body.steps)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    p = Playbook(**body.model_dump())
    db.add(p)
    db.flush()
    return playbook_out(p)


@router.post("/playbooks/{playbook_id}/import", status_code=201)
def playbook_import(playbook_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    t = get_or_404(db, Playbook, playbook_id)
    p = Playbook(name=t.name, description=t.description, category=t.category, steps=list(t.steps or []), settings=dict(t.settings or {}))
    db.add(p)
    db.flush()
    return playbook_out(p)


@router.get("/playbooks/{playbook_id}")
def playbook_get(playbook_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return playbook_out(get_or_404(db, Playbook, playbook_id))


@router.put("/playbooks/{playbook_id}")
def playbook_update(playbook_id: str, body: PlaybookIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    from app.services.playbooks import validate_steps

    p = get_or_404(db, Playbook, playbook_id)
    if p.is_template:
        raise HTTPException(422, "import the template first, then edit your copy")
    try:
        validate_steps(body.steps)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    return playbook_out(p)


@router.delete("/playbooks/{playbook_id}", status_code=204)
def playbook_delete(playbook_id: str, db: Session = Depends(get_db)) -> None:
    p = get_or_404(db, Playbook, playbook_id)
    if p.is_template:
        raise HTTPException(422, "built-in templates cannot be deleted")
    soft_delete(db, p)


class RunIn(BaseModel):
    product_ids: list[str] = Field(min_length=1, max_length=50)
    brand_id: str | None = None


@router.post("/playbooks/{playbook_id}/run", status_code=201)
def playbook_run(playbook_id: str, body: RunIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    from app.services.playbooks import run_playbook

    p = get_or_404(db, Playbook, playbook_id)
    try:
        b = run_playbook(db, p, body.product_ids, brand_id=body.brand_id, max_jobs=get_settings().max_jobs_per_batch)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return {"batch_id": b.id, "total": b.total}


# ---------------------------------------------------------------- Scale: apply design to a different product
class ApplyIn(BaseModel):
    document_ids: list[str] = Field(min_length=1, max_length=20)
    product_ids: list[str] = Field(min_length=1, max_length=50)


@router.post("/scale/apply", status_code=201)
def apply_to_products(body: ApplyIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    from app.imaging.render import render_png
    from app.services.assets import create_asset_from_bytes
    from app.services.playbooks import apply_document_to_product

    if len(body.document_ids) * len(body.product_ids) > 100:
        raise HTTPException(422, "at most 100 designs per run")
    out = []
    for pid in body.product_ids:
        product = get_or_404(db, Product, pid)
        proj = Project(kind="design", name=f"Applied designs — {product.name}"[:200], product_id=pid, brand_id=product.brand_id, data={})
        db.add(proj)
        db.flush()
        for did in body.document_ids:
            get_or_404(db, EditorDocument, did)
            try:
                d = apply_document_to_product(db, did, pid, project_id=proj.id)
            except ValueError as e:
                raise HTTPException(422, str(e)) from e
            a = create_asset_from_bytes(db, render_png(document_json(d)), ext="png", source="generated", filename=f"{d.name}.png",
                                        title=d.name, product_id=pid, project_id=proj.id, provider="shelfcraft", model="design re-use (template renderer)",
                                        meta={"document_id": d.id, "operation": "apply_to_product", "source_document_id": did})
            d.thumbnail_asset_id = a.id
            out.append({"product_id": pid, "document_id": d.id, "asset_id": a.id})
        proj.thumbnail_asset_id = out[-1]["asset_id"] if out else None
    return {"results": out}


# ---------------------------------------------------------------- Media tools
@router.post("/assets/{asset_id}/decompose", status_code=202)
def decompose(asset_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    a = get_or_404(db, Asset, asset_id)
    if a.kind != "image":
        raise HTTPException(422, "only images can be split into layers")
    return job_out(enqueue(db, "decompose_image", {"asset_id": a.id}))


class SpinIn(BaseModel):
    asset_ids: list[str] = Field(min_length=3, max_length=72)
    white_background: bool = True
    fps: int = Field(default=24, ge=8, le=60)
    loops: int = Field(default=3, ge=1, le=10)
    tween: int = Field(default=3, ge=0, le=8)
    title: str | None = Field(default=None, max_length=200)


@router.post("/videos/spin", status_code=202)
def spin(body: SpinIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    for aid in body.asset_ids:
        get_or_404(db, Asset, aid)
    return job_out(enqueue(db, "spin_video", body.model_dump()))


class VoiceoverIn(BaseModel):
    script: list[str] | None = Field(default=None, max_length=30)
    voice: str = Field(default="", max_length=120)
    rate: int = Field(default=175, ge=100, le=260)


@router.post("/videos/{project_id}/voiceover", status_code=202)
def voiceover(project_id: str, body: VoiceoverIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, Project, project_id)
    if not (p.data or {}).get("scenes"):
        raise HTTPException(422, "add scenes first")
    return job_out(enqueue(db, "voiceover_video", {"project_id": p.id, **body.model_dump()}, project_id=p.id))


@router.get("/voices")
def voices() -> list[str]:
    from app.services.media_extra import list_voices

    return list_voices()


# ---------------------------------------------------------------- Scale runs overview (My Runs)
@router.get("/scale/runs")
def scale_runs(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    from sqlalchemy import func

    from app.db.models import Job

    out = []
    for b in db.scalars(select(FactoryBatch).order_by(FactoryBatch.created_at.desc()).limit(50)):
        counts = dict(db.execute(select(Job.status, func.count()).where(Job.batch_id == b.id).group_by(Job.status)).all())
        out.append({"id": b.id, "name": b.name, "total": b.total, "counts": counts, "created_at": b.created_at,
                    "kind": (b.config or {}).get("kind") or ("playbook" if (b.config or {}).get("playbook_id") else "factory")})
    return out


@router.post("/products/{product_id}/images/upload-angles", status_code=201)
def upload_angles(product_id: str, files: list[UploadFile] = File(...), title: str = Form(""), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Upload ordered angle photos for a 360° spin (also attached to the product)."""
    p = get_or_404(db, Product, product_id)
    ids = [create_asset_from_upload(db, f.file, f.filename or "angle.jpg", allowed={"image"}, product_id=p.id, tags=["360"]).id for f in files[:72]]
    return {"asset_ids": ids, "title": title}
