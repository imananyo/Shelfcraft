"""Top-performing listings / competitors per product: import saved pages, browse, benchmark, AI category analysis."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models import CompetitorListing, Product, ProductResearch
from app.db.session import get_db
from app.jobs.queue import enqueue
from app.routers.common import audit, get_or_404
from app.routers.jobs import job_out
from app.services import competitors as cs

router = APIRouter(tags=["competitors"])


class SourceItem(BaseModel):
    name: str = Field(default="page", max_length=200)
    content: str = Field(min_length=1, max_length=8_000_000)


class ImportIn(BaseModel):
    sources: list[SourceItem] = Field(min_length=1, max_length=40)


def _own_ids(p: Product) -> set[str]:
    return {x.upper() for x in (p.asin, (p.specifications or {}).get("Walmart item ID")) if x}


@router.post("/products/{product_id}/competitors/import")
def import_pages(product_id: str, body: ImportIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, Product, product_id)
    own = _own_ids(p)
    results, added_total, updated_total = [], 0, 0
    for s in body.sources:
        try:
            page_type, category, items = cs.parse_page(s.content)
        except cs.CompetitorParseError as e:
            results.append({"name": s.name, "error": str(e)})
            continue
        skipped_own = [i for i in items if str(i.get("market_id") or "").upper() in own]
        items = [i for i in items if i not in skipped_own]
        added, updated = cs.upsert(db, p.id, items)
        added_total, updated_total = added_total + added, updated_total + updated
        results.append({"name": s.name, "page_type": page_type, "category": category, "found": len(items) + len(skipped_own),
                        "added": added, "updated": updated, "skipped_own": len(skipped_own),
                        **({"error": "no listings found on this page"} if not items and not skipped_own else {})})
    total = db.scalar(select(func.count()).select_from(CompetitorListing).where(CompetitorListing.product_id == p.id)) or 0
    audit(db, "import_competitors", "Product", p.id, added=added_total, updated=updated_total)
    if not added_total and not updated_total and all(r.get("error") for r in results):
        raise HTTPException(422, "; ".join(f"{r['name']}: {r['error']}" for r in results)[:1000])
    return {"added": added_total, "updated": updated_total, "total": total, "sources": results}


@router.get("/products/{product_id}/competitors")
def list_competitors(product_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    get_or_404(db, Product, product_id)
    rows = db.scalars(select(CompetitorListing).where(CompetitorListing.product_id == product_id)).all()
    items = sorted((cs.competitor_out(c) for c in rows), key=cs._order)  # noqa: SLF001
    return {"items": items, "total": len(items)}


@router.get("/products/{product_id}/competitors/benchmark")
def get_benchmark(product_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    from app.services.category_analysis import _product_dict

    p = get_or_404(db, Product, product_id)
    rows = db.scalars(select(CompetitorListing).where(CompetitorListing.product_id == product_id)).all()
    return cs.benchmark(_product_dict(p), [cs.competitor_out(c) for c in rows])


class PatchIn(BaseModel):
    included: bool


@router.patch("/products/{product_id}/competitors/{cid}")
def patch_competitor(product_id: str, cid: str, body: PatchIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = db.get(CompetitorListing, cid)
    if c is None or c.product_id != product_id:
        raise HTTPException(404, "competitor not found")
    c.included = body.included
    db.flush()
    return cs.competitor_out(c)


@router.delete("/products/{product_id}/competitors/{cid}", status_code=204)
def delete_competitor(product_id: str, cid: str, db: Session = Depends(get_db)) -> None:
    c = db.get(CompetitorListing, cid)
    if c is None or c.product_id != product_id:
        raise HTTPException(404, "competitor not found")
    db.delete(c)


@router.delete("/products/{product_id}/competitors")
def clear_competitors(product_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    get_or_404(db, Product, product_id)
    n = db.execute(delete(CompetitorListing).where(CompetitorListing.product_id == product_id)).rowcount
    return {"deleted": n}


class AnalyzeIn(BaseModel):
    provider: str | None = None
    max_reviews: int = Field(default=120, ge=0, le=1000)


@router.post("/products/{product_id}/competitors/analyze", status_code=202)
def analyze(product_id: str, body: AnalyzeIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    get_or_404(db, Product, product_id)
    if not db.scalar(select(func.count()).select_from(CompetitorListing).where(
            CompetitorListing.product_id == product_id, CompetitorListing.included.is_(True))):
        raise HTTPException(422, "Add competitor listings first (a saved Best Sellers or search results page).")
    return job_out(enqueue(db, "category_analysis", {"product_id": product_id, **body.model_dump()}))


@router.get("/products/{product_id}/competitors/analysis")
def latest(product_id: str, db: Session = Depends(get_db)) -> dict[str, Any] | None:
    get_or_404(db, Product, product_id)
    r = db.scalars(select(ProductResearch).where(ProductResearch.product_id == product_id, ProductResearch.kind == "category")
                   .order_by(ProductResearch.created_at.desc()).limit(1)).first()
    return None if r is None else {"id": r.id, "result": r.result, "inputs": r.inputs, "provider": r.provider,
                                   "model": r.model, "created_at": r.created_at}
