"""Asset library: list/search/filter, upload, metadata, favorites, folders, download, ZIP, convert."""
from __future__ import annotations

import io
import zipfile
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from PIL import Image
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import Asset, ExportRecord, Folder, ProductImage
from app.db.session import get_db
from app.routers.common import audit, get_or_404
from app.services.assets import asset_url, create_asset_from_upload, load_image, safe_filename, thumb_url
from app.storage.local import get_storage

router = APIRouter(prefix="/assets", tags=["assets"])


def asset_out(a: Asset) -> dict[str, Any]:
    return {
        "id": a.id, "kind": a.kind, "source": a.source, "filename": a.filename, "title": a.title or a.filename,
        "mime_type": a.mime_type, "size_bytes": a.size_bytes, "width": a.width, "height": a.height,
        "duration_s": a.duration_s, "tags": a.tags or [], "favorite": a.favorite, "folder_id": a.folder_id,
        "brand_id": a.brand_id, "product_id": a.product_id, "project_id": a.project_id,
        "provider": a.provider, "model": a.model, "is_ai_generated": a.is_ai_generated,
        "meta": {k: v for k, v in (a.meta or {}).items() if k in
                 ("prompt", "operation", "parent_asset_id", "style", "creative_type", "label", "seed",
                  "native_size", "note", "document_id")},
        "url": asset_url(a.id), "thumb_url": thumb_url(a), "created_at": a.created_at,
    }


@router.get("")
def list_assets(
    q: str | None = None, kind: str | None = None, source: str | None = None, folder_id: str | None = None,
    favorite: bool | None = None, product_id: str | None = None, brand_id: str | None = None,
    tag: str | None = None, ai: bool | None = None, offset: int = 0, limit: int = Query(60, le=200),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    stmt = select(Asset).where(Asset.deleted_at.is_(None), Asset.source != "system")
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Asset.filename.ilike(like), Asset.title.ilike(like)))
    for col, val in ((Asset.kind, kind), (Asset.source, source), (Asset.product_id, product_id),
                     (Asset.brand_id, brand_id)):
        if val:
            stmt = stmt.where(col == val)
    if folder_id:
        stmt = stmt.where(Asset.folder_id == (None if folder_id == "none" else folder_id))
    if favorite is not None:
        stmt = stmt.where(Asset.favorite.is_(favorite))
    if ai is not None:
        stmt = stmt.where(Asset.is_ai_generated.is_(ai))
    rows = db.scalars(stmt.order_by(Asset.created_at.desc())).all()
    if tag:  # JSON column: filter in Python (portable across SQLite/Postgres)
        rows = [a for a in rows if tag in (a.tags or [])]
    total = len(rows)
    return {"items": [asset_out(a) for a in rows[offset: offset + limit]], "total": total}


@router.post("", status_code=201)
def upload_assets(files: list[UploadFile] = File(...), folder_id: str | None = Form(None),
                  product_id: str | None = Form(None), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    if len(files) > 20:
        raise HTTPException(422, "upload at most 20 files at once")
    out = []
    for f in files:
        a = create_asset_from_upload(db, f.file, f.filename or "upload", folder_id=folder_id or None,
                                     product_id=product_id or None)
        out.append(asset_out(a))
    return out


class AssetPatch(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    tags: list[str] | None = Field(default=None, max_length=30)
    favorite: bool | None = None
    folder_id: str | None = None


@router.get("/folders/all")
def list_folders(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    counts = dict(db.execute(select(Asset.folder_id, func.count()).where(Asset.deleted_at.is_(None))
                             .group_by(Asset.folder_id)).all())
    return [{"id": f.id, "name": f.name, "parent_id": f.parent_id, "count": counts.get(f.id, 0)}
            for f in db.scalars(select(Folder).order_by(Folder.name))]


@router.post("/folders", status_code=201)
def create_folder(body: dict[str, str], db: Session = Depends(get_db)) -> dict[str, Any]:
    name = (body.get("name") or "").strip()[:120]
    if not name:
        raise HTTPException(422, "folder name required")
    f = Folder(name=name, parent_id=body.get("parent_id") or None)
    db.add(f)
    db.flush()
    return {"id": f.id, "name": f.name, "parent_id": f.parent_id, "count": 0}


@router.patch("/folders/{folder_id}")
def rename_folder(folder_id: str, body: dict[str, str], db: Session = Depends(get_db)) -> dict[str, Any]:
    f = get_or_404(db, Folder, folder_id)
    f.name = (body.get("name") or f.name).strip()[:120]
    return {"id": f.id, "name": f.name}


@router.delete("/folders/{folder_id}", status_code=204)
def delete_folder(folder_id: str, db: Session = Depends(get_db)) -> None:
    f = get_or_404(db, Folder, folder_id)
    for a in db.scalars(select(Asset).where(Asset.folder_id == f.id)):
        a.folder_id = None
    db.delete(f)


class ZipRequest(BaseModel):
    asset_ids: list[str] = Field(min_length=1, max_length=500)
    name: str = "shelfcraft-assets"


@router.post("/zip")
def zip_assets(body: ZipRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    buf = io.BytesIO()
    used: set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for aid in body.asset_ids:
            a = db.get(Asset, aid)
            if a is None or a.deleted_at:
                continue
            name = safe_filename(a.title or a.filename)
            ext = "." + a.storage_key.rsplit(".", 1)[-1]
            if not name.lower().endswith(ext):
                name += ext
            base, n = name, 1
            while name in used:
                n += 1
                name = base.replace(ext, f"-{n}{ext}")
            used.add(name)
            z.write(get_storage().path(a.storage_key), name)
    db.add(ExportRecord(kind="zip", source_type="assets", params={"count": len(used)}))
    fname = safe_filename(body.name) + ".zip"
    return StreamingResponse(iter([buf.getvalue()]), media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/{asset_id}")
def get_asset(asset_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    a = get_or_404(db, Asset, asset_id)
    out = asset_out(a)
    out["meta_full"] = a.meta or {}
    return out


@router.patch("/{asset_id}")
def update_asset(asset_id: str, body: AssetPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    a = get_or_404(db, Asset, asset_id)
    data = body.model_dump(exclude_unset=True)
    if "folder_id" in data and data["folder_id"]:
        get_or_404(db, Folder, data["folder_id"])
    for k, v in data.items():
        setattr(a, k, v)
    return asset_out(a)


@router.delete("/{asset_id}", status_code=204)
def delete_asset(asset_id: str, db: Session = Depends(get_db)) -> None:
    a = get_or_404(db, Asset, asset_id)
    a.deleted_at = datetime.now(timezone.utc)
    for pi in db.scalars(select(ProductImage).where(ProductImage.asset_id == a.id)):
        db.delete(pi)
    audit(db, "delete", "Asset", a.id)


@router.get("/{asset_id}/file")
def asset_file(asset_id: str, download: bool = False, db: Session = Depends(get_db)) -> FileResponse:
    a = get_or_404(db, Asset, asset_id, include_deleted=True)
    path = get_storage().path(a.storage_key)
    if not path.is_file():
        raise HTTPException(404, "file missing from storage")
    return FileResponse(path, media_type=a.mime_type,
                        filename=safe_filename(a.title or a.filename) if download else None,
                        headers={"Cache-Control": "private, max-age=86400"})


@router.get("/{asset_id}/thumb")
def asset_thumb(asset_id: str, db: Session = Depends(get_db)) -> FileResponse:
    a = get_or_404(db, Asset, asset_id, include_deleted=True)
    key = a.thumb_key or a.storage_key
    return FileResponse(get_storage().path(key), media_type="image/webp" if a.thumb_key else a.mime_type,
                        headers={"Cache-Control": "private, max-age=604800"})


FORMATS = {"png": ("PNG", "image/png"), "jpeg": ("JPEG", "image/jpeg"), "webp": ("WEBP", "image/webp")}


@router.get("/{asset_id}/convert")
def convert_image(asset_id: str, format: str = Query("png", pattern="^(png|jpeg|webp)$"),
                  width: int | None = Query(None, ge=16, le=8000), height: int | None = Query(None, ge=16, le=8000),
                  quality: int = Query(90, ge=40, le=100), max_kb: int | None = Query(None, ge=20, le=20000),
                  background: str = "#ffffff", db: Session = Depends(get_db)) -> Response:
    """Export an image in another format/size. With max_kb, JPEG/WebP quality is reduced to fit."""
    a = get_or_404(db, Asset, asset_id)
    if a.kind != "image":
        raise HTTPException(422, "not an image")
    im = load_image(a)
    if width or height:
        w = width or round(im.width * (height or im.height) / im.height)
        h = height or round(im.height * (width or im.width) / im.width)
        im = im.resize((w, h), Image.LANCZOS)
    pil_fmt, mime = FORMATS[format]
    if pil_fmt == "JPEG":
        im = _flatten(im, background)
    data = _encode(im, pil_fmt, quality)
    if max_kb and pil_fmt != "PNG":
        q = quality
        while len(data) > max_kb * 1024 and q > 40:
            q -= 8
            data = _encode(im, pil_fmt, q)
    db.add(ExportRecord(kind=format, asset_id=a.id, source_type="asset", source_id=a.id,
                        params={"w": im.width, "h": im.height, "bytes": len(data)}))
    name = safe_filename((a.title or a.filename).rsplit(".", 1)[0]) + f".{'jpg' if format == 'jpeg' else format}"
    return Response(data, media_type=mime, headers={
        "Content-Disposition": f'attachment; filename="{name}"',
        "X-Export-Width": str(im.width), "X-Export-Height": str(im.height), "X-Export-Bytes": str(len(data)),
    })


def _flatten(im: Image.Image, bg: str) -> Image.Image:
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        base = Image.new("RGB", im.size, bg if bg.startswith("#") else "#ffffff")
        base.paste(im, mask=im.split()[-1])
        return base
    return im.convert("RGB")


def _encode(im: Image.Image, fmt: str, quality: int) -> bytes:
    buf = io.BytesIO()
    kwargs: dict[str, Any] = {"optimize": True}
    if fmt in ("JPEG", "WEBP"):
        kwargs["quality"] = quality
    im.save(buf, fmt, **kwargs)
    return buf.getvalue()
