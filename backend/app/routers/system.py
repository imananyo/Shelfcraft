"""Health, dashboard, global search, notifications, backups, onboarding."""
from __future__ import annotations

import platform
import shutil
import sqlite3
import sys
import zipfile
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.ai.fallback_manager import image_available, text_available
from app.ai.usage_tracker import usage_summary
from app.config import BACKEND_DIR, get_settings
from app.db.models import (
    Asset,
    Brand,
    CreativeSession,
    EditorDocument,
    Job,
    Notification,
    Product,
    Project,
    UserSettings,
)
from app.db.session import get_db, get_engine
from app.jobs import queue
from app.routers.assets import asset_out
from app.services.assets import thumb_url
from app.services.video import find_tool
from app.storage.local import get_storage

router = APIRouter(tags=["system"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:  # noqa: BLE001
        checks["database"] = f"error: {type(e).__name__}"
    try:
        get_storage().root.exists()
        checks["storage"] = "ok"
    except Exception as e:  # noqa: BLE001
        checks["storage"] = f"error: {type(e).__name__}"
    checks["ffmpeg"] = "ok" if find_tool("ffmpeg") else "missing"
    try:
        httpx.get(f"{get_settings().ollama_base_url}/api/version", timeout=1.5)
        checks["ollama"] = "ok"
    except httpx.HTTPError:
        checks["ollama"] = "offline"
    checks["job_workers"] = len(queue._threads)  # noqa: SLF001 - status only
    ok = checks["database"] == "ok" and checks["storage"] == "ok"
    return {"status": "ok" if ok else "degraded", "checks": checks, "time": datetime.now(timezone.utc)}


@router.get("/capabilities")
def capabilities() -> dict[str, Any]:
    from app.ai.local_diffusion_provider import diffusers_available
    from app.imaging.inpaint import lama_available

    return {
        "text_ai": text_available(),
        "image_ai": image_available(),
        "local_diffusion_installed": diffusers_available(),
        "background_removal": True,
        "object_removal_ai": lama_available(),
        "video": bool(find_tool("ffmpeg")),
        # Real paths on this machine, so the MCP config snippet works on Windows, macOS and Linux.
        "mcp": {"command": sys.executable, "script": str(BACKEND_DIR / "mcp_server.py")},
        # So the UI shows Windows (.ps1) or macOS/Linux (.sh) commands for the computer Shelfcraft runs on.
        "os": {"Windows": "windows", "Darwin": "mac"}.get(platform.system(), "linux"),
    }


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)) -> dict[str, Any]:
    def count(model: Any, *where: Any) -> int:
        stmt = select(func.count()).select_from(model)
        if hasattr(model, "deleted_at"):
            stmt = stmt.where(model.deleted_at.is_(None))
        for w in where:
            stmt = stmt.where(w)
        return db.scalar(stmt) or 0

    settings = db.query(UserSettings).first()
    active = db.get(Brand, settings.active_brand_id) if settings and settings.active_brand_id else None
    recent_projects = db.scalars(select(Project).where(Project.deleted_at.is_(None))
                                 .order_by(Project.updated_at.desc()).limit(6)).all()
    recent_assets = db.scalars(select(Asset).where(Asset.deleted_at.is_(None), Asset.kind == "image",
                                                   Asset.source.in_(("generated", "edited", "export")))
                               .order_by(Asset.created_at.desc()).limit(8)).all()
    jobs = db.scalars(select(Job).order_by(Job.created_at.desc()).limit(8)).all()
    job_counts = dict(db.execute(select(Job.status, func.count()).group_by(Job.status)).all())
    products = db.scalars(select(Product).where(Product.deleted_at.is_(None))
                          .order_by(Product.updated_at.desc()).limit(5)).all()
    n_brands, n_products = count(Brand), count(Product)
    n_generated = count(Asset, Asset.is_ai_generated.is_(True))
    from app.routers.jobs import job_out

    return {
        "counts": {"brands": n_brands, "products": n_products, "projects": count(Project),
                   "assets": count(Asset, Asset.source != "system"), "generated": n_generated,
                   "documents": count(EditorDocument)},
        "active_brand": {"id": active.id, "name": active.name, "colors": active.colors or [],
                         "tagline": active.tagline} if active else None,
        "checklist": [
            {"key": "brand", "label": "Create your brand profile", "done": n_brands > 0, "href": "/brands"},
            {"key": "product", "label": "Add a product with photos", "done": n_products > 0, "href": "/products"},
            {"key": "generate", "label": "Generate your first creative", "done": n_generated > 0, "href": "/create"},
        ],
        "recent_projects": [{"id": p.id, "name": p.name, "kind": p.kind, "updated_at": p.updated_at,
                             "thumb_url": thumb_url(db.get(Asset, p.thumbnail_asset_id)) if p.thumbnail_asset_id else None}
                            for p in recent_projects],
        "recent_assets": [asset_out(a) for a in recent_assets],
        "recent_products": [{"id": p.id, "name": p.name, "category": p.category,
                             "thumb_url": thumb_url(p.images[0].asset) if p.images else None} for p in products],
        "jobs": [job_out(j) for j in jobs],
        "job_counts": job_counts,
        "usage": usage_summary(db, 30),
        "ai": {"text": text_available(), "image": image_available()},
    }


@router.get("/search")
def search(q: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    q = q.strip()
    if len(q) < 2:
        return {"results": []}
    like = f"%{q}%"
    out: list[dict[str, Any]] = []
    for b in db.scalars(select(Brand).where(Brand.deleted_at.is_(None), Brand.name.ilike(like)).limit(5)):
        out.append({"type": "brand", "id": b.id, "title": b.name, "href": f"/brands/{b.id}"})
    for p in db.scalars(select(Product).where(Product.deleted_at.is_(None),
                                              or_(Product.name.ilike(like), Product.sku.ilike(like))).limit(8)):
        out.append({"type": "product", "id": p.id, "title": p.name, "subtitle": p.sku, "href": f"/products/{p.id}"})
    for pr in db.scalars(select(Project).where(Project.deleted_at.is_(None), Project.name.ilike(like)).limit(8)):
        href = {"listing": f"/listings/{pr.id}", "aplus": f"/aplus/{pr.id}", "video": f"/videos/{pr.id}"}.get(
            pr.kind, f"/projects/{pr.id}")
        out.append({"type": "project", "id": pr.id, "title": pr.name, "subtitle": pr.kind, "href": href})
    for a in db.scalars(select(Asset).where(Asset.deleted_at.is_(None), Asset.source != "system",
                                            or_(Asset.title.ilike(like), Asset.filename.ilike(like))).limit(8)):
        out.append({"type": "asset", "id": a.id, "title": a.title or a.filename, "href": f"/library?asset={a.id}",
                    "thumb_url": thumb_url(a)})
    return {"results": out}


@router.get("/sessions")
def sessions(db: Session = Depends(get_db), limit: int = 50) -> list[dict[str, Any]]:
    rows = db.scalars(select(CreativeSession).order_by(CreativeSession.created_at.desc()).limit(limit)).all()
    return [{"id": s.id, "kind": s.kind, "title": s.title, "project_id": s.project_id, "created_at": s.created_at}
            for s in rows]


@router.get("/notifications")
def notifications(db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.scalars(select(Notification).order_by(Notification.created_at.desc()).limit(30)).all()
    unread = db.scalar(select(func.count()).select_from(Notification).where(Notification.read.is_(False))) or 0
    return {"unread": unread, "items": [{"id": n.id, "level": n.level, "title": n.title, "body": n.body,
                                         "link": n.link, "read": n.read, "created_at": n.created_at} for n in rows]}


@router.post("/notifications/read-all")
def read_all(db: Session = Depends(get_db)) -> dict[str, Any]:
    for n in db.scalars(select(Notification).where(Notification.read.is_(False))):
        n.read = True
    return {"ok": True}


@router.post("/onboarding/{key}")
def set_onboarding(key: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = db.query(UserSettings).first()
    assert s is not None
    s.onboarding = {**(s.onboarding or {}), key: True}
    return {"onboarding": s.onboarding}


# ---------------------------------------------------------------- backups
@router.get("/storage")
def storage_usage() -> dict[str, Any]:
    s = get_settings()
    db_file = s.data_dir / "shelfcraft.db"
    return {"media": get_storage().usage_bytes(), "database_bytes": db_file.stat().st_size if db_file.exists() else 0,
            "data_dir": str(s.data_dir)}


@router.get("/backups")
def list_backups() -> list[dict[str, Any]]:
    d = get_settings().backups_dir
    return [{"name": f.name, "size_bytes": f.stat().st_size,
             "created_at": datetime.fromtimestamp(f.stat().st_mtime, timezone.utc)}
            for f in sorted(d.glob("shelfcraft-backup-*.zip"), reverse=True)]


@router.post("/backups", status_code=201)
def create_backup() -> dict[str, Any]:
    """Consistent snapshot: SQLite online-backup API + media files, zipped."""
    s = get_settings()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    tmp_db = s.backups_dir / f"db-{stamp}.sqlite"
    url = get_engine().url
    if url.get_backend_name() != "sqlite" or not url.database:
        raise HTTPException(422, "API backups support SQLite only; use pg_dump for PostgreSQL")
    src = sqlite3.connect(url.database)
    dst = sqlite3.connect(tmp_db)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    out = s.backups_dir / f"shelfcraft-backup-{stamp}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(tmp_db, "shelfcraft.db")
        for f in s.media_dir.rglob("*"):
            if f.is_file() and "tmp" not in f.relative_to(s.media_dir).parts[:1]:
                z.write(f, f"media/{f.relative_to(s.media_dir).as_posix()}")
    tmp_db.unlink(missing_ok=True)
    return {"name": out.name, "size_bytes": out.stat().st_size}


@router.get("/backups/{name}")
def download_backup(name: str) -> FileResponse:
    d = get_settings().backups_dir.resolve()
    p = (d / name).resolve()
    if p.parent != d or not p.name.startswith("shelfcraft-backup-") or not p.is_file():
        raise HTTPException(404, "backup not found")
    return FileResponse(p, media_type="application/zip", filename=p.name)
