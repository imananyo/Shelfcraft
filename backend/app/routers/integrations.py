"""Product import: paste-a-listing (free, offline) and the official Amazon Selling Partner API (your own credentials).

Shelfcraft never scrapes Amazon pages. The SP-API connector uses Amazon's official Catalog Items API with
credentials from YOUR seller account (check Amazon's current SP-API developer terms; not verified by Shelfcraft). Credentials
are stored server-side only and never sent to the browser.
"""
from __future__ import annotations

import re
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.models import ProviderConfig
from app.db.session import get_db
from app.routers.common import audit
from app.routers.products import ProductIn, create_product, product_out

router = APIRouter(tags=["integrations"])

SPAPI = "amazon_spapi"
REGIONS = {"na": "https://sellingpartnerapi-na.amazon.com", "eu": "https://sellingpartnerapi-eu.amazon.com",
           "fe": "https://sellingpartnerapi-fe.amazon.com"}
MARKETPLACE_IDS = {"US": ("ATVPDKIKX0DER", "na"), "CA": ("A2EUQ1WTGCTBG2", "na"), "MX": ("A1AM78C64UM0Y8", "na"),
                   "UK": ("A1F83G8C2ARO7P", "eu"), "DE": ("A1PA6795UKMFR9", "eu"), "FR": ("A13V1IB3VIYZZH", "eu"),
                   "IT": ("APJ6JRA9NG5V4", "eu"), "ES": ("A1RKKUPIHCS9HS", "eu"), "IN": ("A21TJRUUN4KGV", "eu"),
                   "AE": ("A2VIGQ35RCS4UG", "eu"), "JP": ("A1VC38T7YXB528", "fe"), "AU": ("A39IBJ37TRP1C6", "fe")}


# ---------------------------------------------------------------- paste import (no AI, no network)
class PasteIn(BaseModel):
    text: str = Field(min_length=10, max_length=30000)
    brand_id: str | None = None


def parse_listing_text(text: str) -> dict[str, Any]:
    """Heuristic parser for a copied product listing: first meaningful line = title, bullet-like lines = features."""
    lines = [ln.strip() for ln in text.replace("\r", "").split("\n")]
    lines = [ln for ln in lines if ln]
    title = next((ln for ln in lines if 8 <= len(ln) <= 250 and not ln.startswith(("•", "-", "*"))), lines[0][:200])
    bullets, para, specs = [], [], {}
    price = None
    for ln in lines:
        if ln == title:
            continue
        m = re.match(r"^\s*(?:[•\-\*·▪►]|\d+[.)])\s*(.+)$", ln)
        kv = re.match(r"^([A-Za-z][A-Za-z /&]{1,30})\s*[:：]\s*(.{1,80})$", ln)
        pm = re.search(r"(?:[$€£₹]\s?)(\d+(?:[.,]\d{2})?)", ln)
        if pm and price is None and len(ln) < 40:
            price = float(pm.group(1).replace(",", "."))
            continue
        if m:
            bullets.append(m.group(1).strip())
        elif kv and len(ln) < 90 and len(specs) < 20 and not ln.isupper():
            specs[kv.group(1).strip()] = kv.group(2).strip()
        elif len(ln) > 60:
            para.append(ln)
    return {"name": title[:200], "features": bullets[:10], "description": "\n\n".join(para)[:20000] or None,
            "specifications": specs, "price": price}


@router.post("/products/import-text", status_code=201)
def import_text(body: PasteIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    data = parse_listing_text(body.text)
    out = create_product(ProductIn(**data, brand_id=body.brand_id), db)
    audit(db, "import_text", "Product", out["id"])
    return {**out, "parsed": {k: bool(v) for k, v in data.items()},
            "note": "Parsed from pasted text without AI. Review the fields and add photos."}


# ---------------------------------------------------------------- Amazon SP-API connector
class SpapiIn(BaseModel):
    client_id: str | None = Field(default=None, max_length=200)
    client_secret: str | None = Field(default=None, max_length=300)
    refresh_token: str | None = Field(default=None, max_length=2000)
    enabled: bool | None = None


def _cfg(db: Session) -> ProviderConfig:
    row = db.get(ProviderConfig, SPAPI)
    if row is None:
        row = ProviderConfig(name=SPAPI, enabled=False, extra={})
        db.add(row)
        db.flush()
    return row


@router.get("/integrations/amazon")
def spapi_status(db: Session = Depends(get_db)) -> dict[str, Any]:
    row = _cfg(db)
    ex = row.extra or {}
    return {"enabled": row.enabled, "has_client_id": bool(ex.get("client_id")), "has_client_secret": bool(row.api_key),
            "has_refresh_token": bool(ex.get("refresh_token")), "last_error": row.last_error, "last_success_at": row.last_success_at,
            "marketplaces": list(MARKETPLACE_IDS),
            "note": "Uses Amazon's official Selling Partner API with your own seller credentials (check Amazon's current developer terms). "
                    "Shelfcraft never scrapes Amazon pages."}


@router.patch("/integrations/amazon")
def spapi_update(body: SpapiIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = _cfg(db)
    ex = dict(row.extra or {})
    if body.client_id is not None:
        ex["client_id"] = body.client_id.strip() or None
    if body.refresh_token is not None:
        ex["refresh_token"] = body.refresh_token.strip() or None
    if body.client_secret is not None:
        row.api_key = body.client_secret.strip() or None
    if body.enabled is not None:
        row.enabled = body.enabled
    row.extra = {k: v for k, v in ex.items() if v}
    return spapi_status(db)


def _access_token(row: ProviderConfig) -> str:
    ex = row.extra or {}
    if not (ex.get("client_id") and row.api_key and ex.get("refresh_token")):
        raise HTTPException(422, "Amazon connector isn't configured (Settings → Integrations)")
    try:
        r = httpx.post("https://api.amazon.com/auth/o2/token", timeout=20,
                       data={"grant_type": "refresh_token", "refresh_token": ex["refresh_token"], "client_id": ex["client_id"],
                             "client_secret": row.api_key})
    except httpx.HTTPError as e:
        raise HTTPException(502, f"couldn't reach Amazon login: {type(e).__name__}") from e
    if r.status_code != 200:
        raise HTTPException(502, f"Amazon rejected the credentials (HTTP {r.status_code})")
    return r.json()["access_token"]


class AsinIn(BaseModel):
    asin: str = Field(pattern=r"^[A-Z0-9]{10}$")
    country: str = Field(default="US", max_length=4)
    brand_id: str | None = None
    download_images: bool = True


@router.post("/integrations/amazon/import", status_code=201)
def import_asin(body: AsinIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    from datetime import datetime, timezone

    from app.db.models import Product, ProductImage
    from app.services.assets import create_asset_from_bytes, sniff

    row = _cfg(db)
    if not row.enabled:
        raise HTTPException(422, "enable the Amazon connector in Settings → Integrations first")
    if body.country not in MARKETPLACE_IDS:
        raise HTTPException(422, f"unsupported country {body.country}")
    mid, region = MARKETPLACE_IDS[body.country]
    token = _access_token(row)
    try:
        r = httpx.get(f"{REGIONS[region]}/catalog/2022-04-01/items/{body.asin}", timeout=30, headers={"x-amz-access-token": token},
                      params={"marketplaceIds": mid, "includedData": "summaries,images,attributes"})
    except httpx.HTTPError as e:
        raise HTTPException(502, f"couldn't reach the Selling Partner API: {type(e).__name__}") from e
    if r.status_code == 404:
        raise HTTPException(404, "ASIN not found in that marketplace")
    if r.status_code >= 400:
        row.last_error = f"HTTP {r.status_code}"
        raise HTTPException(502, f"Selling Partner API error (HTTP {r.status_code})")
    item = r.json()
    summ = (item.get("summaries") or [{}])[0]
    attrs = item.get("attributes") or {}
    bullets = [b.get("value") for b in attrs.get("bullet_point", []) if b.get("value")]
    desc = next((d.get("value") for d in attrs.get("product_description", []) if d.get("value")), None)
    out = create_product(ProductIn(name=(summ.get("itemName") or body.asin)[:200], asin=body.asin, brand_id=body.brand_id,
                                   category=summ.get("browseClassification", {}).get("displayName"), features=bullets[:10],
                                   description=desc), db)
    images_added = 0
    if body.download_images:
        p = db.get(Product, out["id"])
        urls = [im["link"] for grp in item.get("images") or [] for im in grp.get("images", []) if im.get("height", 0) >= 500][:8]
        for i, url in enumerate(dict.fromkeys(urls)):
            try:
                data = httpx.get(url, timeout=30).content
                kind, ext, _ = sniff(data[:64], "img.jpg")
                if kind != "image":
                    continue
                a = create_asset_from_bytes(db, data, ext=ext, source="upload", area="uploads", filename=f"{body.asin}-{i}.{ext}",
                                            product_id=p.id, tags=["amazon"])
                db.add(ProductImage(product_id=p.id, asset_id=a.id, role="main" if i == 0 else "reference", position=i))
                images_added += 1
            except (httpx.HTTPError, ValueError):
                continue
        db.flush()
        db.refresh(p)
        out = product_out(db, p)
    row.last_success_at, row.last_error = datetime.now(timezone.utc), None
    return {**out, "images_imported": images_added, "source": "Amazon Selling Partner API (Catalog Items)"}
