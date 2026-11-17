"""Share links: a no-login, read-only gallery of one project's visuals (like Pixii's "share link")."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Asset, Brand, Project
from app.db.session import get_db
from app.routers.common import audit, get_or_404
from app.storage.local import get_storage

router = APIRouter(tags=["share"])


def _share_out(p: Project) -> dict[str, Any]:
    sh = (p.data or {}).get("share") or {}
    return {"enabled": bool(sh.get("token")), "token": sh.get("token"), "url": f"/share/{sh['token']}" if sh.get("token") else None,
            "created_at": sh.get("created_at")}


@router.get("/projects/{project_id}/share")
def share_status(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return _share_out(get_or_404(db, Project, project_id))


@router.post("/projects/{project_id}/share")
def share_create(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, Project, project_id)
    data = dict(p.data or {})
    if not (data.get("share") or {}).get("token"):
        data["share"] = {"token": secrets.token_urlsafe(18), "created_at": datetime.now(timezone.utc).isoformat()}
        p.data = data
        audit(db, "share_create", "Project", p.id)
    return _share_out(p)


@router.delete("/projects/{project_id}/share")
def share_revoke(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, Project, project_id)
    data = dict(p.data or {})
    data.pop("share", None)
    p.data = data
    audit(db, "share_revoke", "Project", p.id)
    return _share_out(p)


def _project_by_token(db: Session, token: str) -> Project:
    if len(token) < 16:
        raise HTTPException(404, "link not found")
    for p in db.scalars(select(Project).where(Project.deleted_at.is_(None))):
        sh = (p.data or {}).get("share") or {}
        if sh.get("token") and secrets.compare_digest(str(sh["token"]), token):
            return p
    raise HTTPException(404, "This share link was revoked or never existed.")


def _shared_assets(db: Session, p: Project) -> list[Asset]:
    return list(db.scalars(select(Asset).where(Asset.project_id == p.id, Asset.deleted_at.is_(None),
                                               Asset.kind.in_(("image", "video"))).order_by(Asset.created_at)))


@router.get("/share/{token}")
def share_view(token: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """PUBLIC (no login). Only this project's images/videos and its listing copy are exposed."""
    p = _project_by_token(db, token)
    brand = db.get(Brand, p.brand_id) if p.brand_id else None
    base = f"/api/share/{token}/assets"
    items = [{"id": a.id, "kind": a.kind, "title": a.title or a.filename, "width": a.width, "height": a.height,
              "url": f"{base}/{a.id}", "thumb_url": f"{base}/{a.id}?thumb=1", "ai": a.is_ai_generated}
             for a in _shared_assets(db, p)]
    copy = (p.data or {}).get("copy") if p.kind == "listing" else None
    return {"title": p.name, "kind": p.kind, "brand": brand.name if brand else None, "items": items, "copy": copy,
            "created_at": p.created_at}


@router.get("/share/{token}/assets/{asset_id}")
def share_asset(token: str, asset_id: str, thumb: bool = False, download: bool = False, db: Session = Depends(get_db)) -> FileResponse:
    p = _project_by_token(db, token)
    a = db.get(Asset, asset_id)
    if a is None or a.deleted_at or a.project_id != p.id:
        raise HTTPException(404, "not part of this share")
    key = (a.thumb_key or a.storage_key) if thumb else a.storage_key
    path = get_storage().path(key)
    if not path.is_file():
        raise HTTPException(404, "file missing")
    return FileResponse(path, media_type=("image/webp" if thumb and a.thumb_key else a.mime_type),
                        filename=(a.title or a.filename) if download else None, headers={"Cache-Control": "public, max-age=3600"})
