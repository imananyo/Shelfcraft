"""Product workspace: CRUD, variants, images, search/filter/sort, CSV import/export, URL metadata."""
from __future__ import annotations

import csv
import io
import json
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import Asset, Brand, Product, ProductImage, ProductVariant
from app.db.session import get_db
from app.routers.common import apply_updates, audit, get_or_404, soft_delete
from app.services.assets import asset_url, create_asset_from_upload, thumb_url

router = APIRouter(prefix="/products", tags=["products"])


class VariantIn(BaseModel):
    id: str | None = None
    name: str = Field(min_length=1, max_length=120)
    sku: str | None = Field(default=None, max_length=80)
    attributes: dict[str, str] = Field(default_factory=dict)
    price: float | None = Field(default=None, ge=0)


class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    brand_id: str | None = None
    sku: str | None = Field(default=None, max_length=80)
    asin: str | None = Field(default=None, max_length=20)
    source_url: str | None = Field(default=None, max_length=1000)
    category: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=20000)
    features: list[str] = Field(default_factory=list, max_length=30)
    benefits: list[str] = Field(default_factory=list, max_length=30)
    specifications: dict[str, str] = Field(default_factory=dict)
    price: float | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", max_length=8)
    tags: list[str] = Field(default_factory=list, max_length=30)
    variants: list[VariantIn] | None = None


class ProductPatch(ProductIn):
    name: str | None = Field(default=None, min_length=1, max_length=200)  # type: ignore[assignment]


def product_out(db: Session, p: Product, *, full: bool = True) -> dict[str, Any]:
    images = []
    for pi in p.images:
        a = pi.asset
        if a and not a.deleted_at:
            images.append({"id": pi.id, "asset_id": a.id, "role": pi.role, "position": pi.position,
                           "url": asset_url(a.id), "thumb_url": thumb_url(a), "width": a.width, "height": a.height})
    brand = db.get(Brand, p.brand_id) if p.brand_id else None
    out: dict[str, Any] = {
        "id": p.id, "name": p.name, "brand_id": p.brand_id, "brand_name": brand.name if brand else None,
        "sku": p.sku, "asin": p.asin, "category": p.category, "price": p.price, "currency": p.currency,
        "tags": p.tags or [], "images": images, "image_count": len(images),
        "cover_url": images[0]["thumb_url"] if images else None,
        "variant_count": len(p.variants), "created_at": p.created_at, "updated_at": p.updated_at,
    }
    if full:
        out.update({
            "source_url": p.source_url, "description": p.description, "features": p.features or [],
            "benefits": p.benefits or [], "specifications": p.specifications or {},
            "variants": [{"id": v.id, "name": v.name, "sku": v.sku, "attributes": v.attributes or {},
                          "price": v.price} for v in p.variants],
        })
    return out


def _sync_variants(p: Product, variants: list[VariantIn]) -> None:
    existing = {v.id: v for v in p.variants}
    keep: list[ProductVariant] = []
    for v in variants:
        if v.id and v.id in existing:
            row = existing[v.id]
            row.name, row.sku, row.attributes, row.price = v.name, v.sku, v.attributes, v.price
        else:
            row = ProductVariant(name=v.name, sku=v.sku, attributes=v.attributes, price=v.price)
        keep.append(row)
    p.variants = keep


@router.get("")
def list_products(
    q: str | None = None, brand_id: str | None = None, category: str | None = None,
    sort: str = Query("updated", pattern="^(updated|created|name|price)$"),
    limit: int = Query(200, le=500), db: Session = Depends(get_db),
) -> dict[str, Any]:
    stmt = select(Product).where(Product.deleted_at.is_(None))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Product.name.ilike(like), Product.sku.ilike(like), Product.category.ilike(like),
                              Product.asin.ilike(like)))
    if brand_id:
        stmt = stmt.where(Product.brand_id == brand_id)
    if category:
        stmt = stmt.where(Product.category == category)
    order = {"updated": Product.updated_at.desc(), "created": Product.created_at.desc(),
             "name": Product.name.asc(), "price": Product.price.asc()}[sort]
    rows = db.scalars(stmt.order_by(order).limit(limit)).all()
    categories = sorted({c for c in db.scalars(select(Product.category).where(
        Product.deleted_at.is_(None), Product.category.is_not(None))).all() if c})
    return {"items": [product_out(db, p, full=False) for p in rows], "categories": categories}


@router.post("", status_code=201)
def create_product(body: ProductIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    data = body.model_dump(exclude={"variants"})
    if data["brand_id"]:
        get_or_404(db, Brand, data["brand_id"])
    p = Product(**data)
    if body.variants:
        _sync_variants(p, body.variants)
    db.add(p)
    db.flush()
    audit(db, "create", "Product", p.id)
    return product_out(db, p)


@router.get("/export.csv")
def export_csv(db: Session = Depends(get_db)) -> StreamingResponse:
    rows = db.scalars(select(Product).where(Product.deleted_at.is_(None)).order_by(Product.name)).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_COLUMNS)
    for p in rows:
        brand = db.get(Brand, p.brand_id) if p.brand_id else None
        w.writerow([p.name, p.sku or "", p.asin or "", brand.name if brand else "", p.category or "",
                    p.price if p.price is not None else "", p.currency, p.description or "",
                    " | ".join(p.features or []), " | ".join(p.benefits or []),
                    json.dumps(p.specifications or {}, ensure_ascii=False), ", ".join(p.tags or []),
                    p.source_url or ""])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="shelfcraft-products.csv"'})


CSV_COLUMNS = ["name", "sku", "asin", "brand", "category", "price", "currency", "description", "features",
               "benefits", "specifications", "tags", "source_url"]


@router.post("/import.csv")
def import_csv(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    raw = file.file.read(5 * 1024 * 1024 + 1)
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(422, "CSV larger than 5 MB")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise HTTPException(422, "CSV must be UTF-8") from e
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "name" not in [f.strip().lower() for f in reader.fieldnames]:
        raise HTTPException(422, "CSV needs at least a 'name' column")
    brands = {b.name.lower(): b.id for b in db.scalars(select(Brand).where(Brand.deleted_at.is_(None)))}
    created, updated, errors = 0, 0, []
    for i, raw_row in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw_row.items()}
        if not row.get("name"):
            errors.append({"line": i, "error": "missing name"})
            continue
        try:
            price = float(row["price"]) if row.get("price") else None
        except ValueError:
            errors.append({"line": i, "error": f"invalid price '{row['price']}'"})
            continue
        try:
            specs = json.loads(row["specifications"]) if row.get("specifications") else {}
            if not isinstance(specs, dict):
                raise ValueError
        except ValueError:
            specs = {}
        data = {
            "name": row["name"][:200], "sku": row.get("sku") or None, "asin": row.get("asin") or None,
            "brand_id": brands.get(row.get("brand", "").lower()), "category": row.get("category") or None,
            "price": price, "currency": (row.get("currency") or "USD")[:8],
            "description": row.get("description") or None,
            "features": [s.strip() for s in row.get("features", "").split("|") if s.strip()],
            "benefits": [s.strip() for s in row.get("benefits", "").split("|") if s.strip()],
            "specifications": {str(k): str(v) for k, v in specs.items()},
            "tags": [s.strip() for s in row.get("tags", "").split(",") if s.strip()],
            "source_url": row.get("source_url") or None,
        }
        existing = db.scalar(select(Product).where(Product.sku == data["sku"], Product.deleted_at.is_(None))) \
            if data["sku"] else None
        if existing:
            apply_updates(existing, data)
            updated += 1
        else:
            db.add(Product(**data))
            created += 1
    db.flush()
    audit(db, "import_csv", "Product", None, created=created, updated=updated, errors=len(errors))
    return {"created": created, "updated": updated, "errors": errors[:50]}


@router.post("/fetch-url")
def fetch_url_metadata(body: dict[str, str]) -> dict[str, Any]:
    from app.services.web_extract import extract_product_from_url

    return extract_product_from_url(body.get("url", ""))


@router.get("/{product_id}")
def get_product(product_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return product_out(db, get_or_404(db, Product, product_id))


@router.patch("/{product_id}")
def update_product(product_id: str, body: ProductPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, Product, product_id)
    data = body.model_dump(exclude_unset=True, exclude={"variants"})
    if data.get("brand_id"):
        get_or_404(db, Brand, data["brand_id"])
    apply_updates(p, data)
    if body.variants is not None:
        _sync_variants(p, body.variants)
    audit(db, "update", "Product", p.id)
    return product_out(db, p)


@router.delete("/{product_id}", status_code=204)
def delete_product(product_id: str, db: Session = Depends(get_db)) -> None:
    soft_delete(db, get_or_404(db, Product, product_id))


@router.post("/{product_id}/duplicate", status_code=201)
def duplicate_product(product_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    src = get_or_404(db, Product, product_id)
    p = Product(name=f"{src.name} (copy)"[:200], brand_id=src.brand_id, category=src.category,
                description=src.description, features=list(src.features or []), benefits=list(src.benefits or []),
                specifications=dict(src.specifications or {}), price=src.price, currency=src.currency,
                tags=list(src.tags or []))
    db.add(p)
    db.flush()
    for pi in src.images:
        db.add(ProductImage(product_id=p.id, asset_id=pi.asset_id, role=pi.role, position=pi.position))
    db.flush()
    db.refresh(p)
    return product_out(db, p)


@router.post("/{product_id}/images", status_code=201)
def upload_images(product_id: str, files: list[UploadFile] = File(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, Product, product_id)
    if len(files) > 12:
        raise HTTPException(422, "upload at most 12 images at once")
    start = max((pi.position for pi in p.images), default=-1) + 1
    for i, f in enumerate(files):
        a = create_asset_from_upload(db, f.file, f.filename or "image", allowed={"image"},
                                     product_id=p.id, brand_id=p.brand_id, tags=["product"])
        db.add(ProductImage(product_id=p.id, asset_id=a.id, role="main" if not p.images and i == 0 else "reference",
                            position=start + i))
    db.flush()
    db.refresh(p)
    return product_out(db, p)


@router.post("/{product_id}/images/attach", status_code=201)
def attach_asset(product_id: str, body: dict[str, str], db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, Product, product_id)
    a = get_or_404(db, Asset, body.get("asset_id", ""))
    if a.kind != "image":
        raise HTTPException(422, "only images can be attached")
    pos = max((pi.position for pi in p.images), default=-1) + 1
    db.add(ProductImage(product_id=p.id, asset_id=a.id, role=body.get("role", "reference"), position=pos))
    db.flush()
    db.refresh(p)
    return product_out(db, p)


@router.put("/{product_id}/images/order")
def reorder_images(product_id: str, body: dict[str, list[str]], db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, Product, product_id)
    order = body.get("image_ids", [])
    by_id = {pi.id: pi for pi in p.images}
    for pos, iid in enumerate(order):
        if iid in by_id:
            by_id[iid].position = pos
            by_id[iid].role = "main" if pos == 0 else ("reference" if by_id[iid].role == "main" else by_id[iid].role)
    db.flush()
    db.refresh(p)
    return product_out(db, p)


@router.delete("/{product_id}/images/{image_id}", status_code=204)
def remove_image(product_id: str, image_id: str, db: Session = Depends(get_db)) -> None:
    pi = get_or_404(db, ProductImage, image_id)
    if pi.product_id != product_id:
        raise HTTPException(404, "image not found")
    db.delete(pi)
