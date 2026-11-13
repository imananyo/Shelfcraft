"""Brand workspace: CRUD, logo & guideline uploads, website auto-fill, active brand."""
from __future__ import annotations

import io
import re
from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Asset, Brand, BrandGuideline, Product, UserSettings
from app.db.session import get_db
from app.routers.common import apply_updates, audit, get_or_404, soft_delete
from app.services.assets import create_asset_from_upload, get_storage, thumb_url

router = APIRouter(prefix="/brands", tags=["brands"])

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class BrandIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    website: str | None = Field(default=None, max_length=500)
    colors: list[str] = Field(default_factory=list, max_length=6)
    primary_font: str | None = Field(default=None, max_length=80)
    secondary_font: str | None = Field(default=None, max_length=80)
    language: str = Field(default="en", max_length=16)
    tagline: str | None = Field(default=None, max_length=200)
    tone_of_voice: str | None = Field(default=None, max_length=300)
    target_audience: str | None = Field(default=None, max_length=4000)
    positioning: str | None = Field(default=None, max_length=4000)
    values: list[str] = Field(default_factory=list, max_length=6)
    aesthetic: list[str] = Field(default_factory=list, max_length=6)
    visual_identity: str | None = Field(default=None, max_length=4000)
    marketing_guidelines: str | None = Field(default=None, max_length=8000)
    extra_details: str | None = Field(default=None, max_length=8000)

    @field_validator("colors")
    @classmethod
    def _colors(cls, v: list[str]) -> list[str]:
        for c in v:
            if not HEX.match(c):
                raise ValueError(f"'{c}' is not a #RRGGBB color")
        return [c.lower() for c in v]

    @field_validator("values", "aesthetic")
    @classmethod
    def _chips(cls, v: list[str]) -> list[str]:
        return [s.strip()[:60] for s in v if s.strip()]


class BrandPatch(BrandIn):
    name: str | None = Field(default=None, min_length=1, max_length=120)  # type: ignore[assignment]


def brand_out(db: Session, b: Brand) -> dict[str, Any]:
    logo = db.get(Asset, b.logo_asset_id) if b.logo_asset_id else None
    product_count = db.scalar(select(func.count()).select_from(Product)
                              .where(Product.brand_id == b.id, Product.deleted_at.is_(None))) or 0
    return {
        "id": b.id, "name": b.name, "website": b.website, "colors": b.colors or [],
        "primary_font": b.primary_font, "secondary_font": b.secondary_font, "language": b.language,
        "tagline": b.tagline, "tone_of_voice": b.tone_of_voice, "target_audience": b.target_audience,
        "positioning": b.positioning, "values": b.values or [], "aesthetic": b.aesthetic or [],
        "visual_identity": b.visual_identity, "marketing_guidelines": b.marketing_guidelines,
        "extra_details": b.extra_details, "logo_asset_id": b.logo_asset_id,
        "logo_url": thumb_url(logo) if logo else None,
        "guidelines": [{"id": g.id, "title": g.title, "asset_id": g.asset_id,
                        "chars": len(g.extracted_text or ""), "created_at": g.created_at}
                       for g in b.guidelines],
        "product_count": product_count, "created_at": b.created_at, "updated_at": b.updated_at,
    }


@router.get("")
def list_brands(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(Brand).where(Brand.deleted_at.is_(None)).order_by(Brand.created_at)).all()
    return [brand_out(db, b) for b in rows]


@router.post("", status_code=201)
def create_brand(body: BrandIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    b = Brand(**body.model_dump())
    db.add(b)
    db.flush()
    settings = db.query(UserSettings).first()
    if settings and not settings.active_brand_id:
        settings.active_brand_id = b.id
    audit(db, "create", "Brand", b.id)
    return brand_out(db, b)


@router.get("/{brand_id}")
def get_brand(brand_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return brand_out(db, get_or_404(db, Brand, brand_id))


@router.patch("/{brand_id}")
def update_brand(brand_id: str, body: BrandPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    b = get_or_404(db, Brand, brand_id)
    apply_updates(b, body.model_dump(exclude_unset=True))
    audit(db, "update", "Brand", b.id)
    return brand_out(db, b)


@router.delete("/{brand_id}", status_code=204)
def delete_brand(brand_id: str, db: Session = Depends(get_db)) -> None:
    b = get_or_404(db, Brand, brand_id)
    soft_delete(db, b)
    settings = db.query(UserSettings).first()
    if settings and settings.active_brand_id == b.id:
        nxt = db.scalar(select(Brand.id).where(Brand.deleted_at.is_(None), Brand.id != b.id).limit(1))
        settings.active_brand_id = nxt


@router.post("/{brand_id}/activate")
def activate_brand(brand_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    b = get_or_404(db, Brand, brand_id)
    settings = db.query(UserSettings).first()
    assert settings is not None
    settings.active_brand_id = b.id
    return {"active_brand_id": b.id}


@router.post("/{brand_id}/logo")
def upload_logo(brand_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    b = get_or_404(db, Brand, brand_id)
    asset = create_asset_from_upload(db, file.file, file.filename or "logo.png", allowed={"image"},
                                     brand_id=b.id, title=f"{b.name} logo", tags=["logo"])
    b.logo_asset_id = asset.id
    return brand_out(db, b)


@router.post("/{brand_id}/guidelines", status_code=201)
def upload_guideline(brand_id: str, file: UploadFile = File(...), title: str = Form(""),
                     db: Session = Depends(get_db)) -> dict[str, Any]:
    b = get_or_404(db, Brand, brand_id)
    asset = create_asset_from_upload(db, file.file, file.filename or "guidelines", allowed={"document"},
                                     brand_id=b.id, tags=["guidelines"])
    text = extract_document_text(asset)
    g = BrandGuideline(brand_id=b.id, asset_id=asset.id, title=(title or asset.filename)[:200], extracted_text=text)
    db.add(g)
    db.flush()
    return {"id": g.id, "title": g.title, "chars": len(text or ""), "preview": (text or "")[:500]}


@router.delete("/{brand_id}/guidelines/{guideline_id}", status_code=204)
def delete_guideline(brand_id: str, guideline_id: str, db: Session = Depends(get_db)) -> None:
    g = get_or_404(db, BrandGuideline, guideline_id)
    if g.brand_id == brand_id:
        db.delete(g)


@router.post("/autofill")
def autofill_from_website(body: dict[str, str], db: Session = Depends(get_db)) -> dict[str, Any]:
    """Best-effort public metadata extraction (no login, no bypass). Returns suggestions only."""
    from app.services.web_extract import extract_brand_from_url

    return extract_brand_from_url(body.get("url", ""))


def extract_document_text(asset: Asset) -> str:
    data = get_storage().read_bytes(asset.storage_key)
    if asset.mime_type == "application/pdf":
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(data))
            return "\n".join((p.extract_text() or "") for p in reader.pages[:60])[:100_000]
        except Exception:  # noqa: BLE001 - malformed PDFs shouldn't fail the upload
            return ""
    return data.decode("utf-8", errors="replace")[:100_000]


def brand_context(db: Session, brand_id: str | None) -> str:
    """Compact brand description injected into every generation prompt."""
    if not brand_id:
        return ""
    b = db.get(Brand, brand_id)
    if b is None or b.deleted_at:
        return ""
    parts = [f"Brand: {b.name}"]
    for label, val in (("Tagline", b.tagline), ("Tone of voice", b.tone_of_voice),
                       ("Target audience", b.target_audience), ("Positioning", b.positioning),
                       ("Visual identity", b.visual_identity), ("Marketing guidelines", b.marketing_guidelines),
                       ("Extra", b.extra_details)):
        if val:
            parts.append(f"{label}: {val}")
    if b.values:
        parts.append("Values: " + ", ".join(b.values))
    if b.aesthetic:
        parts.append("Aesthetic: " + ", ".join(b.aesthetic))
    if b.colors:
        parts.append("Brand colors: " + ", ".join(b.colors))
    guide = " ".join((g.extracted_text or "")[:1500] for g in b.guidelines[:2]).strip()
    if guide:
        parts.append(f"Guideline excerpts: {guide[:2500]}")
    return "\n".join(parts)
