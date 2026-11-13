"""Public REST API v1 (API-key authenticated). Mounted at /v1 with its own docs at /v1/docs.

Keys are created in Settings → API & MCP. Send `Authorization: Bearer sk_shelf_...`.
Scopes: `read` (GET) and `write` (create/generate). Per-key rate limit: 120 requests/minute.
The existing local app API under /api is unchanged.
"""
from __future__ import annotations

import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ApiKey
from app.db.session import get_db

KEY_PREFIX = "sk_shelf_"
RATE_PER_MIN = 120
_hits: dict[str, deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def new_key() -> tuple[str, str, str]:
    raw = KEY_PREFIX + secrets.token_urlsafe(32)
    return raw, raw[:14], hash_key(raw)


class KeyContext:
    def __init__(self, key: ApiKey) -> None:
        self.id, self.name, self.scopes = key.id, key.name, set(key.scopes or [])

    def require(self, scope: str) -> None:
        if scope not in self.scopes:
            raise HTTPException(403, f"this API key lacks the '{scope}' scope")


def api_key_auth(request: Request, authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> KeyContext:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing 'Authorization: Bearer sk_shelf_…' header")
    raw = authorization.split(" ", 1)[1].strip()
    key = db.scalar(select(ApiKey).where(ApiKey.key_hash == hash_key(raw)))
    if key is None or key.revoked_at is not None:
        raise HTTPException(401, "invalid or revoked API key")
    now = time.monotonic()
    with _lock:
        q = _hits[key.id]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= RATE_PER_MIN:
            raise HTTPException(429, f"rate limit: {RATE_PER_MIN} requests per minute per key")
        q.append(now)
    key.last_used_at = datetime.now(timezone.utc)
    key.request_count = (key.request_count or 0) + 1
    ctx = KeyContext(key)
    ctx.require("read" if request.method in ("GET", "HEAD") else "write")
    return ctx


router = APIRouter(dependencies=[Depends(api_key_auth)])


# ---------------------------------------------------------------- catalog
@router.get("/brands", tags=["Catalog"], summary="List brands")
def list_brands(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    from app.routers.brands import list_brands as _list

    return _list(db)


@router.get("/products", tags=["Catalog"], summary="List / search products")
def list_products(q: str | None = None, limit: int = 100, db: Session = Depends(get_db)) -> dict[str, Any]:
    from app.routers.products import list_products as _list

    return _list(q=q, brand_id=None, category=None, sort="updated", limit=min(limit, 500), db=db)


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    brand_id: str | None = None
    sku: str | None = None
    category: str | None = None
    description: str | None = None
    features: list[str] = Field(default_factory=list)
    benefits: list[str] = Field(default_factory=list)
    specifications: dict[str, str] = Field(default_factory=dict)
    price: float | None = None
    currency: str = "USD"


@router.post("/products", tags=["Catalog"], status_code=201, summary="Create a product")
def create_product(body: ProductCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    from app.routers.products import ProductIn, create_product as _create

    return _create(ProductIn(**body.model_dump()), db)


@router.get("/products/{product_id}", tags=["Catalog"], summary="Get a product")
def get_product(product_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    from app.routers.products import get_product as _get

    return _get(product_id, db)


# ---------------------------------------------------------------- listings
class ListingCreate(BaseModel):
    product_id: str
    marketplace: str = Field(default="amazon", pattern="^(amazon|amazon_mobile|shopify|walmart|tiktok)$")
    country: str = "US"
    language: str = "en"
    audience: str | None = None
    tone: str | None = None
    keywords: str | None = None


@router.post("/listings", tags=["Listings"], status_code=201, summary="Create a listing and start generating its copy (async)")
def create_listing(body: ListingCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    from app.routers.listings import ListingIn, create_listing as _create

    return _create(ListingIn(**body.model_dump(), generate=True), db)


@router.get("/listings/{listing_id}", tags=["Listings"], summary="Get a listing (copy, warnings, images, jobs)")
def get_listing(listing_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    from app.routers.listings import get_listing as _get

    return _get(listing_id, db)


@router.post("/listings/{listing_id}/translate", tags=["Listings"], status_code=202, summary="Translate a listing (async)")
def translate_listing(listing_id: str, language: str, country: str = "US", db: Session = Depends(get_db)) -> dict[str, Any]:
    from app.routers.growth import TranslateIn, translate as _tr

    return _tr(listing_id, TranslateIn(language=language, country=country), db)


@router.post("/grader", tags=["Listings"], summary="Grade a listing (synchronous)")
def grade(body: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
    from app.routers.growth import GradeIn, grade_payload

    return grade_payload(db, GradeIn(**body))


# ---------------------------------------------------------------- creatives & jobs
class CreativeCreate(BaseModel):
    creative_type: str
    product_id: str | None = None
    brand_id: str | None = None
    width: int = 1024
    height: int = 1024
    style: str = "minimal"
    extra_prompt: str = ""
    count: int = Field(default=1, ge=1, le=4)


@router.post("/creatives", tags=["Creatives"], status_code=202, summary="Generate creatives (async; poll the jobs)")
def create_creative(body: CreativeCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    from app.routers.creative import GenerateIn, generate

    return generate(GenerateIn(**body.model_dump()), db)


@router.get("/jobs/{job_id}", tags=["Jobs"], summary="Job status / result")
def get_job(job_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    from app.routers.jobs import get_job as _get

    return _get(job_id, db)


@router.get("/assets/{asset_id}", tags=["Assets"], summary="Asset metadata (incl. provider/model attribution)")
def get_asset(asset_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    from app.routers.assets import get_asset as _get

    out = _get(asset_id, db)
    out["download_url"] = f"/v1/assets/{asset_id}/file"
    return out


@router.get("/assets/{asset_id}/file", tags=["Assets"], summary="Download the asset file")
def asset_file(asset_id: str, db: Session = Depends(get_db)) -> FileResponse:
    from app.routers.assets import asset_file as _file

    return _file(asset_id, True, db)


def build_public_app() -> FastAPI:
    sub = FastAPI(title="Shelfcraft Public API", version="1.0.0",
                  description="Programmatic access to your local Shelfcraft workspace. Authenticate with `Authorization: Bearer sk_shelf_…` "
                              "(create keys in Settings → API & MCP). All AI runs on free or local providers only.")
    sub.include_router(router)

    @sub.exception_handler(Exception)
    async def _err(_r: Request, e: Exception) -> JSONResponse:
        from app.ai.base import NoProviderAvailable

        if isinstance(e, NoProviderAvailable):
            return JSONResponse({"detail": str(e)}, status_code=503)
        return JSONResponse({"detail": "internal error"}, status_code=500)

    return sub


# ---------------------------------------------------------------- key management (local app API, under /api)
manage = APIRouter(prefix="/api-keys", tags=["api-keys"])


def key_out(k: ApiKey) -> dict[str, Any]:
    return {"id": k.id, "name": k.name, "prefix": k.prefix, "scopes": k.scopes or [], "created_at": k.created_at,
            "last_used_at": k.last_used_at, "request_count": k.request_count, "revoked": k.revoked_at is not None}


class KeyIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[str] = Field(default_factory=lambda: ["read", "write"])


@manage.get("")
def keys(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [key_out(k) for k in db.scalars(select(ApiKey).order_by(ApiKey.created_at.desc()))]


@manage.post("", status_code=201)
def create_key(body: KeyIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    scopes = sorted({s for s in body.scopes if s in ("read", "write")}) or ["read"]
    raw, prefix, h = new_key()
    k = ApiKey(name=body.name, prefix=prefix, key_hash=h, scopes=scopes)
    db.add(k)
    db.flush()
    return {**key_out(k), "key": raw, "note": "Copy this key now — it won't be shown again."}


@manage.delete("/{key_id}")
def revoke_key(key_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    k = db.get(ApiKey, key_id)
    if k is None:
        raise HTTPException(404, "key not found")
    k.revoked_at = datetime.now(timezone.utc)
    return key_out(k)
