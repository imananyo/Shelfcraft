"""Product import: paste-a-listing (free, offline) and the official Amazon Selling Partner API (your own credentials).

Without the connector, ASIN / Walmart imports read the public product page (services/marketplace_scrape.py).
The SP-API connector uses Amazon's official Catalog Items API with
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
from app.routers.common import audit, get_or_404
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
                    "Without it, ASIN imports read the public product page instead."}


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


# ---------------------------------------------------------------- unified "import from" (ASIN · Walmart ID · URL)
ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")
WALMART_ID_RE = re.compile(r"^\d{6,14}$")
AMAZON_URL_ASIN = re.compile(r"(?:/dp/|/gp/product/|/gp/aw/d/|/product/|/ASIN/)([A-Z0-9]{10})(?:[/?#]|$)", re.I)
WALMART_URL_ID = re.compile(r"/ip/(?:[^/?#]+/)?(\d{6,14})(?:[/?#]|$)", re.I)
AMAZON_DOMAINS = {"US": "amazon.com", "UK": "amazon.co.uk", "CA": "amazon.ca", "DE": "amazon.de", "FR": "amazon.fr",
                  "ES": "amazon.es", "IT": "amazon.it", "IN": "amazon.in", "JP": "amazon.co.jp", "AU": "amazon.com.au",
                  "MX": "amazon.com.mx", "AE": "amazon.ae"}


class SourceIn(BaseModel):
    kind: str = Field(pattern=r"^(asin|walmart|url)$")
    value: str = Field(min_length=1, max_length=1000)
    country: str = Field(default="US", max_length=4)
    brand_id: str | None = None


def classify_source(kind: str, value: str) -> tuple[str, str]:
    """Normalize user input to ("asin", ASIN) | ("walmart", item id) | ("url", url). Marketplace URLs are mapped
    to their identifier so we never fetch Amazon/Walmart pages."""
    v = value.strip()
    if kind == "asin":
        m = AMAZON_URL_ASIN.search(v)
        v = (m.group(1) if m else v).upper()
        if not ASIN_RE.match(v):
            raise HTTPException(422, "An ASIN is 10 letters/digits, e.g. B08N5WRWNW (or paste an Amazon product link).")
        return "asin", v
    if kind == "walmart":
        m = WALMART_URL_ID.search(v)
        v = m.group(1) if m else v
        if not WALMART_ID_RE.match(v):
            raise HTTPException(422, "A Walmart item ID is 6–14 digits, e.g. 5129928603 (or paste a walmart.com/ip/… link).")
        return "walmart", v
    host = (re.sub(r"^https?://", "", v, flags=re.I).split("/")[0]).lower()
    if "amazon." in host or "amzn." in host:
        m = AMAZON_URL_ASIN.search(v)
        if not m:
            raise HTTPException(422, "Couldn't find an ASIN in that Amazon link — paste the ASIN directly instead.")
        return "asin", m.group(1).upper()
    if "walmart." in host:
        m = WALMART_URL_ID.search(v)
        if not m:
            raise HTTPException(422, "Couldn't find an item ID in that Walmart link — paste the item ID directly instead.")
        return "walmart", m.group(1)
    return "url", v


def _download_image(db: Session, product_id: str, url: str, tag: str) -> bool:
    from app.db.models import ProductImage
    from app.services.assets import create_asset_from_bytes, sniff
    from app.services.web_extract import ExtractError, _check_url

    try:
        safe = _check_url(url)
        r = httpx.get(safe, timeout=20, follow_redirects=False)
        if r.status_code != 200 or len(r.content) > 15_000_000:
            return False
        kind, ext, _ = sniff(r.content[:64], "img.jpg")
        if kind != "image":
            return False
        a = create_asset_from_bytes(db, r.content, ext=ext, source="upload", area="uploads", filename=f"import.{ext}",
                                    product_id=product_id, tags=[tag])
        db.add(ProductImage(product_id=product_id, asset_id=a.id, role="main", position=0))
        db.flush()
        return True
    except (ExtractError, httpx.HTTPError, ValueError):
        return False


IMAGE_CDN_HOSTS = ("media-amazon.com", "ssl-images-amazon.com", "images-amazon.com", "walmartimages.com")


def _import_marketplace_page(db: Session, market: str, ident: str, url: str, brand_id: str | None) -> dict[str, Any]:
    """Read the public product page; if the marketplace blocks us, still save the product with its ID."""
    from app.services import marketplace_scrape as ms

    label = "Amazon" if market == "amazon" else "Walmart"
    id_spec = {} if market == "amazon" else {"Walmart item ID": ident}
    try:
        data = (ms.parse_amazon if market == "amazon" else ms.parse_walmart)(ms.fetch_page(url))
    except ms.ScrapeError as e:
        out = create_product(ProductIn(name=f"{label} product {ident}", asin=ident if market == "amazon" else None,
                                       source_url=url, brand_id=brand_id, specifications=id_spec, tags=[market]), db)
        audit(db, "import_source", "Product", out["id"], kind=market, scraped=False)
        return {**out, "import": {"kind": "asin" if market == "amazon" else "walmart", "id": ident, "complete": False,
                                  "blocked": True, "page_url": url,
                                  "note": f"Saved with the {label} ID, but couldn't read the product page: {e}. "
                                          f"Finish the import from your own browser: open the {label} page, then save "
                                          "or copy it into Shelfcraft (steps below)."}}
    return _save_marketplace_data(db, market, ident, url, data, brand_id)


def _save_marketplace_data(db: Session, market: str, ident: str, url: str, data: dict[str, Any], brand_id: str | None,
                           product_id: str | None = None, via: str = "product page") -> dict[str, Any]:
    """Create (or fill in an existing) product from parsed marketplace page data, import its images, and queue
    Deep Strategy on its reviews."""
    from urllib.parse import urlparse

    from app.db.models import Product, ProductImage
    from app.routers.products import ProductPatch, update_product
    from app.services import marketplace_scrape as ms
    from app.services.assets import create_asset_from_bytes, sniff

    label = "Amazon" if market == "amazon" else "Walmart"
    id_spec = {} if market == "amazon" else {"Walmart item ID": ident}
    specs = {**id_spec, **{k: v for k, v in (data.get("specifications") or {}).items() if k and v}}
    if data.get("brand"):
        specs.setdefault("Brand", data["brand"][:200])
    if data.get("rating"):
        specs["Customer rating"] = f"{data['rating']:g} / 5" + (f" ({data['review_count']} reviews)" if data.get("review_count") else "")
    fields: dict[str, Any] = dict(
        name=data["name"][:200], asin=ident if market == "amazon" else None, source_url=url,
        category=(data.get("category") or None) and data["category"][:120],
        description=(data.get("description") or None) and data["description"][:20000],
        features=[f[:500] for f in (data.get("features") or [])][:10],
        specifications={k[:60]: str(v)[:200] for k, v in list(specs.items())[:30]},
        price=data.get("price"), currency=(data.get("currency") or "USD")[:8])
    if product_id:  # fill in the placeholder saved when the automatic read was blocked
        existing = db.get(Product, product_id)
        fields["specifications"] = {**(existing.specifications or {}), **fields["specifications"]} if existing else fields["specifications"]
        fields["tags"] = sorted(set((existing.tags if existing else None) or []) | {market})
        if brand_id:
            fields["brand_id"] = brand_id
        out = update_product(product_id, ProductPatch(**fields), db)
    else:
        out = create_product(ProductIn(**fields, brand_id=brand_id, tags=[market]), db)
    p = db.get(Product, out["id"])
    start = len([i for i in p.images if i.role != "cutout"])
    images = 0
    for i, img in enumerate(data.get("images") or []):
        host = (urlparse(img).hostname or "").lower()
        if not img.startswith("https://") or not any(host == h or host.endswith("." + h) for h in IMAGE_CDN_HOSTS):
            continue
        raw = ms.download_image(img)
        if not raw:
            continue
        try:
            kind, ext, _ = sniff(raw[:64], "img.jpg")
            if kind != "image":
                continue
            a = create_asset_from_bytes(db, raw, ext=ext, source="upload", area="uploads", filename=f"{ident}-{i}.{ext}",
                                        product_id=p.id, tags=[market])
        except ValueError:
            continue
        db.add(ProductImage(product_id=p.id, asset_id=a.id, role="main" if start + images == 0 else "reference",
                            position=start + images))
        images += 1
    db.flush()
    db.refresh(p)
    out = product_out(db, p)
    research_job = None
    if data.get("reviews"):  # "reads your reviews": store them, then queue Deep Strategy on them
        from app.jobs.queue import enqueue
        from app.services.reviews import save_reviews

        save_reviews(db, p.id, data["reviews"], market)

        research_job = enqueue(db, "product_research", {"product_id": p.id, "reviews": ms.reviews_text(data["reviews"]),
                                                        "competitors": "", "notes": f"Reviews read from the {label} {via}.",
                                                        "provider": None}).id
    audit(db, "import_source", "Product", out["id"], kind=market, scraped=True, images=images, via=via)
    got = [x for x, ok in (("title", True), ("bullets", bool(data.get("features"))), ("description", bool(data.get("description"))),
                           ("price", data.get("price") is not None), ("specs", bool(data.get("specifications"))),
                           (f"{images} image(s)", images > 0),
                           (f"{len(data.get('reviews') or [])} reviews (Deep Strategy is analysing them)", bool(data.get("reviews")))) if ok]
    return {**out, "images_imported": images, "reviews_imported": len(data.get("reviews") or []), "research_job_id": research_job,
            "import": {"kind": "asin" if market == "amazon" else "walmart", "id": ident, "complete": True,
                       "note": f"Imported from the {label} {via}: {', '.join(got)}. Review before generating."}}


class PageHtmlIn(BaseModel):
    html: str = Field(min_length=1, max_length=8_000_000)
    brand_id: str | None = None
    product_id: str | None = None  # fill in this product (e.g. the placeholder saved after a blocked import)


@router.post("/products/import-html", status_code=201)
def import_html(body: PageHtmlIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Import from a product page the user opened in their own browser and saved / copied (page source).

    This is the fallback when our single automated request is answered with a bot check: the user visits the page
    as a normal shopper, and Shelfcraft only parses what they hand over. Nothing is fetched except product images
    from the marketplace image CDN.
    """
    from app.db.models import Product
    from app.services import marketplace_scrape as ms

    try:
        market, ident, url = ms.identify_page(body.html)
        data = (ms.parse_amazon if market == "amazon" else ms.parse_walmart)(body.html)
    except ms.ScrapeError as e:
        raise HTTPException(422, str(e)[:1].upper() + str(e)[1:] + ".") from e
    url_to_keep = url
    if body.product_id:
        existing = get_or_404(db, Product, body.product_id)
        url_to_keep = existing.source_url or url
        expected = existing.asin if market == "amazon" else (existing.specifications or {}).get("Walmart item ID")
        if expected and expected.upper() != ident.upper():
            raise HTTPException(422, f"This page is for {'ASIN' if market == 'amazon' else 'Walmart item'} {ident}, "
                                     f"but this product is {expected}. Open the right product page and try again.")
    return _save_marketplace_data(db, market, ident, url_to_keep, data,
                                  body.brand_id, product_id=body.product_id, via="page you saved from your browser")


@router.post("/products/import-source", status_code=201)
def import_source(body: SourceIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    from app.db.models import Product
    from app.services.web_extract import extract_product_from_url

    kind, ident = classify_source(body.kind, body.value)
    country = body.country if body.country in MARKETPLACE_IDS else "US"

    if kind == "asin":
        row = _cfg(db)
        if row.enabled:
            out = import_asin(AsinIn(asin=ident, country=country, brand_id=body.brand_id), db)
            return {**out, "import": {"kind": "asin", "id": ident, "complete": True,
                                      "note": "Imported title, bullets, description and images via Amazon's Selling Partner API."}}
        url = f"https://www.{AMAZON_DOMAINS.get(country, 'amazon.com')}/dp/{ident}"
        return _import_marketplace_page(db, "amazon", ident, url, body.brand_id)

    if kind == "walmart":
        return _import_marketplace_page(db, "walmart", ident, f"https://www.walmart.com/ip/{ident}", body.brand_id)

    res = extract_product_from_url(ident)
    if not res.get("ok"):
        raise HTTPException(422, res.get("error") or "couldn't read that page")
    s = res["suggestions"]
    out = create_product(ProductIn(name=(s.get("name") or "Imported product")[:200], description=s.get("description"),
                                   source_url=(s.get("source_url") or ident)[:1000], price=s.get("price"),
                                   currency=(s.get("currency") or "USD")[:8], brand_id=body.brand_id,
                                   category=(s.get("category") or None) and s["category"][:120],
                                   specifications={"Brand": s["brand"][:200]} if s.get("brand") else {}), db)
    got_image = bool(s.get("image_url")) and _download_image(db, out["id"], s["image_url"], "url-import")
    if got_image:
        p = db.get(Product, out["id"])
        db.refresh(p)
        out = product_out(db, p)
    audit(db, "import_source", "Product", out["id"], kind="url")
    return {**out, "import": {"kind": "url", "id": res["source"], "complete": True, "image_imported": got_image,
                              "note": "Filled from the page's public metadata. Review the details before generating."}}
