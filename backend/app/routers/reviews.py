"""Customer reviews per product: import from saved pages / CSV / pasted text, browse, stats, AI analysis."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.db.models import Product, ProductResearch, ProductReview
from app.db.session import get_db
from app.jobs.queue import enqueue
from app.routers.common import audit, get_or_404
from app.routers.jobs import job_out
from app.services import reviews as rv

router = APIRouter(tags=["reviews"])

MAX_SOURCES = 40


class SourceItem(BaseModel):
    name: str = Field(default="pasted", max_length=200)
    kind: str = Field(default="auto", pattern=r"^(auto|html|csv|text)$")
    content: str = Field(min_length=1, max_length=8_000_000)


class ImportIn(BaseModel):
    sources: list[SourceItem] = Field(min_length=1, max_length=MAX_SOURCES)


@router.post("/products/{product_id}/reviews/import")
def import_reviews(product_id: str, body: ImportIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, Product, product_id)
    own_id = (p.asin or (p.specifications or {}).get("Walmart item ID") or "").upper()
    results, added_total, dupes_total = [], 0, 0
    for s in body.sources:
        entry: dict[str, Any] = {"name": s.name, "found": 0, "added": 0, "duplicates": 0}
        try:
            found, info = rv.parse_source(s.kind, s.content)
        except rv.ReviewParseError as e:
            results.append({**entry, "error": str(e)})
            continue
        source = info.get("market") or "paste"
        if info.get("id") and own_id and info["id"].upper() != own_id:
            entry["warning"] = (f"this page is for {info['id']}, not {own_id}; its reviews were still added "
                                "(variations of one listing often share reviews)")
        if not found:
            entry["error"] = ("no reviews found. For Amazon, open the 'See more reviews' page (or a star filter) and "
                              "save that page" if source == "amazon" else "no reviews found in this file")
        else:
            added, dupes = rv.save_reviews(db, p.id, found, source)
            entry.update(found=len(found), added=added, duplicates=dupes, source=source)
            added_total, dupes_total = added_total + added, dupes_total + dupes
        results.append(entry)
    total = db.scalar(select(func.count()).select_from(ProductReview).where(ProductReview.product_id == p.id)) or 0
    audit(db, "import_reviews", "Product", p.id, added=added_total, duplicates=dupes_total)
    if added_total == 0 and all(r.get("error") for r in results):
        raise HTTPException(422, "; ".join(f"{r['name']}: {r['error']}" for r in results)[:1000])
    return {"added": added_total, "duplicates": dupes_total, "total": total, "sources": results}


@router.get("/products/{product_id}/reviews")
def list_reviews(product_id: str, rating: int | None = Query(default=None, ge=1, le=5), q: str | None = None,
                 offset: int = Query(default=0, ge=0), limit: int = Query(default=20, ge=1, le=100),
                 db: Session = Depends(get_db)) -> dict[str, Any]:
    get_or_404(db, Product, product_id)
    stmt = select(ProductReview).where(ProductReview.product_id == product_id)
    if rating:
        stmt = stmt.where(ProductReview.rating >= rating - 0.5, ProductReview.rating < rating + 0.5)
    if q:
        like = f"%{q.strip()[:100]}%"
        stmt = stmt.where(or_(ProductReview.text.ilike(like), ProductReview.title.ilike(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(ProductReview.review_date.desc().nulls_last(), ProductReview.created_at.desc())
                      .offset(offset).limit(limit)).all()
    return {"items": [rv.review_out(r) for r in rows], "total": total}


@router.get("/products/{product_id}/reviews/stats")
def review_stats(product_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    get_or_404(db, Product, product_id)
    rows = db.scalars(select(ProductReview).where(ProductReview.product_id == product_id)).all()
    return rv.review_stats([rv.review_out(r) for r in rows])


@router.delete("/products/{product_id}/reviews/{review_id}", status_code=204)
def delete_review(product_id: str, review_id: str, db: Session = Depends(get_db)) -> None:
    r = db.get(ProductReview, review_id)
    if r is None or r.product_id != product_id:
        raise HTTPException(404, "review not found")
    db.delete(r)


@router.delete("/products/{product_id}/reviews")
def clear_reviews(product_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    get_or_404(db, Product, product_id)
    n = db.execute(delete(ProductReview).where(ProductReview.product_id == product_id)).rowcount
    audit(db, "clear_reviews", "Product", product_id, deleted=n)
    return {"deleted": n}


class AnalyzeIn(BaseModel):
    provider: str | None = None
    max_reviews: int = Field(default=400, ge=10, le=2000)


@router.post("/products/{product_id}/reviews/analyze", status_code=202)
def analyze(product_id: str, body: AnalyzeIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    get_or_404(db, Product, product_id)
    if not db.scalar(select(func.count()).select_from(ProductReview).where(ProductReview.product_id == product_id)):
        raise HTTPException(422, "Add reviews first (saved review pages, a CSV export or pasted reviews).")
    job = enqueue(db, "review_analysis", {"product_id": product_id, **body.model_dump()})
    return job_out(job)


@router.get("/products/{product_id}/reviews/analysis")
def latest_analysis(product_id: str, db: Session = Depends(get_db)) -> dict[str, Any] | None:
    get_or_404(db, Product, product_id)
    r = db.scalars(select(ProductResearch).where(ProductResearch.product_id == product_id, ProductResearch.kind == "reviews")
                   .order_by(ProductResearch.created_at.desc()).limit(1)).first()
    if r is None:
        return None
    return {"id": r.id, "result": r.result, "inputs": r.inputs, "provider": r.provider, "model": r.model,
            "created_at": r.created_at}
