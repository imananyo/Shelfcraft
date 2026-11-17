"""Design projects, editor documents (autosave/versioning/revisions), templates, document export."""
from __future__ import annotations

import io
import zipfile
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Asset, EditorDocument, EditorRevision, ExportRecord, Project, Template
from app.db.session import get_db
from app.imaging.render import render_document
from app.routers.common import get_or_404, soft_delete
from app.services.assets import create_asset_from_bytes, thumb_url
from app.services.documents import VersionConflict, create_document, document_json, save_document

router = APIRouter(tags=["editor"])


# ---------------------------------------------------------------- projects
def project_out(db: Session, p: Project) -> dict[str, Any]:
    docs = db.scalars(select(EditorDocument).where(EditorDocument.project_id == p.id,
                                                   EditorDocument.deleted_at.is_(None))
                      .order_by(EditorDocument.created_at)).all()
    thumb = db.get(Asset, p.thumbnail_asset_id) if p.thumbnail_asset_id else None
    return {"id": p.id, "name": p.name, "kind": p.kind, "brand_id": p.brand_id, "product_id": p.product_id,
            "data": p.data or {}, "thumb_url": thumb_url(thumb) if thumb else None,
            "documents": [doc_summary(db, d) for d in docs], "created_at": p.created_at, "updated_at": p.updated_at}


def doc_summary(db: Session, d: EditorDocument) -> dict[str, Any]:
    thumb = db.get(Asset, d.thumbnail_asset_id) if d.thumbnail_asset_id else None
    return {"id": d.id, "name": d.name, "width": d.width, "height": d.height, "version": d.version,
            "project_id": d.project_id, "thumb_url": thumb_url(thumb) if thumb else None, "updated_at": d.updated_at}


@router.get("/projects")
def list_projects(kind: str | None = None, q: str | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    stmt = select(Project).where(Project.deleted_at.is_(None))
    if kind:
        stmt = stmt.where(Project.kind == kind)
    if q:
        stmt = stmt.where(Project.name.ilike(f"%{q}%"))
    out = []
    for p in db.scalars(stmt.order_by(Project.updated_at.desc())).all():
        thumb = db.get(Asset, p.thumbnail_asset_id) if p.thumbnail_asset_id else None
        n_docs = len(db.scalars(select(EditorDocument.id).where(EditorDocument.project_id == p.id,
                                                                EditorDocument.deleted_at.is_(None))).all())
        out.append({"id": p.id, "name": p.name, "kind": p.kind, "product_id": p.product_id,
                    "thumb_url": thumb_url(thumb) if thumb else None, "document_count": n_docs,
                    "updated_at": p.updated_at})
    return out


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: str = Field(default="design", pattern="^(design|aplus|video|inspire)$")
    brand_id: str | None = None
    product_id: str | None = None
    width: int | None = Field(default=None, ge=16, le=8000)
    height: int | None = Field(default=None, ge=16, le=8000)
    template_id: str | None = None


@router.post("/projects", status_code=201)
def create_project(body: ProjectIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = Project(name=body.name, kind=body.kind, brand_id=body.brand_id, product_id=body.product_id, data={})
    db.add(p)
    db.flush()
    if body.kind == "design":
        if body.template_id:
            t = get_or_404(db, Template, body.template_id)
            doc = t.document
        else:
            doc = {"width": body.width or 2000, "height": body.height or 2000, "background": "#ffffff", "layers": []}
        create_document(db, name=body.name, doc=doc, project_id=p.id)
    return project_out(db, p)


@router.get("/projects/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return project_out(db, get_or_404(db, Project, project_id))


@router.patch("/projects/{project_id}")
def patch_project(project_id: str, body: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, Project, project_id)
    if "name" in body:
        name = str(body["name"]).strip()[:200]
        if not name:
            raise HTTPException(422, "name required")
        p.name = name
    if isinstance(body.get("data"), dict):
        p.data = {**(p.data or {}), **body["data"]}
    for k in ("brand_id", "product_id"):
        if k in body:
            setattr(p, k, body[k] or None)
    return project_out(db, p)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, db: Session = Depends(get_db)) -> None:
    soft_delete(db, get_or_404(db, Project, project_id))


@router.post("/projects/{project_id}/duplicate", status_code=201)
def duplicate_project(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    src = get_or_404(db, Project, project_id)
    p = Project(name=f"{src.name} (copy)"[:200], kind=src.kind, brand_id=src.brand_id, product_id=src.product_id,
                data=dict(src.data or {}), thumbnail_asset_id=src.thumbnail_asset_id)
    db.add(p)
    db.flush()
    for d in db.scalars(select(EditorDocument).where(EditorDocument.project_id == src.id,
                                                     EditorDocument.deleted_at.is_(None))):
        create_document(db, name=d.name, doc=document_json(d), project_id=p.id)
    return project_out(db, p)


# ---------------------------------------------------------------- documents
@router.get("/documents")
def list_documents(project_id: str | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    stmt = select(EditorDocument).where(EditorDocument.deleted_at.is_(None))
    if project_id:
        stmt = stmt.where(EditorDocument.project_id == project_id)
    return [doc_summary(db, d) for d in db.scalars(stmt.order_by(EditorDocument.updated_at.desc()).limit(200))]


class DocIn(BaseModel):
    name: str = Field(default="Untitled design", max_length=200)
    project_id: str | None = None
    document: dict[str, Any] | None = None
    width: int = Field(default=2000, ge=16, le=8000)
    height: int = Field(default=2000, ge=16, le=8000)
    template_id: str | None = None


@router.post("/documents", status_code=201)
def new_document(body: DocIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    if body.template_id:
        doc = get_or_404(db, Template, body.template_id).document
    else:
        doc = body.document or {"width": body.width, "height": body.height, "background": "#ffffff", "layers": []}
    project_id = body.project_id
    if not project_id:
        p = Project(name=body.name, kind="design", data={})
        db.add(p)
        db.flush()
        project_id = p.id
    try:
        d = create_document(db, name=body.name, doc=doc, project_id=project_id)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return {**doc_summary(db, d), "document": document_json(d)}


@router.get("/documents/{doc_id}")
def get_document(doc_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    d = get_or_404(db, EditorDocument, doc_id)
    return {**doc_summary(db, d), "document": document_json(d)}


class SaveIn(BaseModel):
    document: dict[str, Any]
    base_version: int | None = None
    name: str | None = Field(default=None, max_length=200)
    checkpoint: bool = False  # store a revision snapshot before saving
    thumbnail: bool = False   # re-render thumbnail (on manual save)


@router.put("/documents/{doc_id}")
def save_doc(doc_id: str, body: SaveIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    d = get_or_404(db, EditorDocument, doc_id)
    if body.name:
        d.name = body.name
    try:
        d = save_document(db, d, body.document, base_version=body.base_version, revision=body.checkpoint)
    except VersionConflict as e:
        raise HTTPException(409, {"message": str(e), "server_version": e.current}) from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    if body.thumbnail:
        _refresh_thumbnail(db, d)
    return doc_summary(db, d)


def _refresh_thumbnail(db: Session, d: EditorDocument) -> None:
    im = render_document(document_json(d), scale=min(1.0, 640 / max(d.width, d.height)))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    a = create_asset_from_bytes(db, buf.getvalue(), ext="png", source="system", area="thumbs",
                                filename=f"{d.name}-thumb.png", meta={"document_id": d.id})
    d.thumbnail_asset_id = a.id
    if d.project_id:
        p = db.get(Project, d.project_id)
        if p:
            p.thumbnail_asset_id = a.id


@router.delete("/documents/{doc_id}", status_code=204)
def delete_document(doc_id: str, db: Session = Depends(get_db)) -> None:
    soft_delete(db, get_or_404(db, EditorDocument, doc_id))


@router.get("/documents/{doc_id}/revisions")
def revisions(doc_id: str, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(EditorRevision).where(EditorRevision.document_id == doc_id)
                      .order_by(EditorRevision.created_at.desc())).all()
    return [{"id": r.id, "version": r.version, "created_at": r.created_at,
             "layers": len((r.snapshot or {}).get("layers", []))} for r in rows]


@router.post("/documents/{doc_id}/revisions/{rev_id}/restore")
def restore_revision(doc_id: str, rev_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    d = get_or_404(db, EditorDocument, doc_id)
    r = get_or_404(db, EditorRevision, rev_id)
    if r.document_id != d.id:
        raise HTTPException(404, "revision not found")
    d = save_document(db, d, r.snapshot, base_version=None, revision=True)
    return {**doc_summary(db, d), "document": document_json(d)}


@router.get("/documents/{doc_id}/export")
def export_document(doc_id: str, format: str = Query("png", pattern="^(png|jpeg|webp|json|svg)$"),
                    scale: float = Query(1.0, ge=0.1, le=2.0), quality: int = Query(92, ge=40, le=100),
                    save: bool = False, db: Session = Depends(get_db)) -> Response:
    d = get_or_404(db, EditorDocument, doc_id)
    doc = document_json(d)
    safe = "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in d.name)[:80] or "design"
    if format == "json":
        import json

        return Response(json.dumps({"shelfcraft_document": 1, "name": d.name, **doc}, ensure_ascii=False),
                        media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{safe}.json"'})
    if format == "svg":  # layered vector export for Figma / Illustrator / Canva / Inkscape
        from app.imaging.svg_export import document_to_svg

        svg = document_to_svg(doc).encode("utf-8")
        db.add(ExportRecord(kind="svg", source_type="document", source_id=d.id, params={"bytes": len(svg)}))
        return Response(svg, media_type="image/svg+xml", headers={"Content-Disposition": f'attachment; filename="{safe}.svg"'})
    im = render_document(doc, scale=scale)
    buf = io.BytesIO()
    if format == "jpeg":
        im.convert("RGB").save(buf, "JPEG", quality=quality, optimize=True)
    elif format == "webp":
        im.save(buf, "WEBP", quality=quality)
    else:
        im.save(buf, "PNG", optimize=True)
    data = buf.getvalue()
    ext = "jpg" if format == "jpeg" else format
    if save:
        create_asset_from_bytes(db, data, ext=ext, source="export", filename=f"{safe}.{ext}", title=d.name,
                                project_id=d.project_id, meta={"document_id": d.id, "operation": "export"})
    db.add(ExportRecord(kind=format, source_type="document", source_id=d.id,
                        params={"w": im.width, "h": im.height, "bytes": len(data)}))
    return Response(data, media_type=f"image/{format}", headers={
        "Content-Disposition": f'attachment; filename="{safe}.{ext}"', "X-Export-Width": str(im.width),
        "X-Export-Height": str(im.height), "X-Export-Bytes": str(len(data))})


@router.post("/documents/import", status_code=201)
def import_document(body: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
    if body.get("shelfcraft_document") != 1:
        raise HTTPException(422, "not a Shelfcraft document export")
    doc = {k: body[k] for k in ("width", "height", "background", "layers") if k in body}
    p = Project(name=str(body.get("name") or "Imported design")[:200], kind="design", data={})
    db.add(p)
    db.flush()
    try:
        d = create_document(db, name=p.name, doc=doc, project_id=p.id)
    except (ValueError, KeyError) as e:
        raise HTTPException(422, f"invalid document: {e}") from e
    return doc_summary(db, d)


@router.post("/projects/{project_id}/export.zip")
def export_project_zip(project_id: str, db: Session = Depends(get_db)) -> StreamingResponse:
    p = get_or_404(db, Project, project_id)
    docs = db.scalars(select(EditorDocument).where(EditorDocument.project_id == p.id,
                                                   EditorDocument.deleted_at.is_(None))
                      .order_by(EditorDocument.created_at)).all()
    if not docs:
        raise HTTPException(422, "project has no documents to export")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for i, d in enumerate(docs, 1):
            im = render_document(document_json(d))
            b = io.BytesIO()
            im.save(b, "PNG", optimize=True)
            safe = "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in d.name)[:60]
            z.writestr(f"{i:02d}-{safe}.png", b.getvalue())
    db.add(ExportRecord(kind="zip", source_type="project", source_id=p.id, params={"documents": len(docs)}))
    safe = "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in p.name)[:80]
    return StreamingResponse(iter([buf.getvalue()]), media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{safe}.zip"'})


# ---------------------------------------------------------------- templates
@router.get("/templates")
def list_templates(category: str | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    stmt = select(Template).where(Template.deleted_at.is_(None))
    if category:
        stmt = stmt.where(Template.category == category)
    return [{"id": t.id, "name": t.name, "category": t.category, "width": t.width, "height": t.height,
             "is_builtin": t.is_builtin, "layer_count": len((t.document or {}).get("layers", [])),
             "thumb_url": thumb_url(db.get(Asset, t.thumbnail_asset_id)) if t.thumbnail_asset_id else None}
            for t in db.scalars(stmt.order_by(Template.is_builtin.desc(), Template.name))]


@router.get("/templates/{template_id}")
def get_template(template_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    t = get_or_404(db, Template, template_id)
    return {"id": t.id, "name": t.name, "category": t.category, "width": t.width, "height": t.height,
            "document": t.document, "is_builtin": t.is_builtin}


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(default="custom", max_length=40)
    document_id: str


@router.post("/templates", status_code=201)
def save_as_template(body: TemplateIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    d = get_or_404(db, EditorDocument, body.document_id)
    doc = document_json(d)
    t = Template(name=body.name, category=body.category, width=d.width, height=d.height, document=doc,
                 thumbnail_asset_id=d.thumbnail_asset_id)
    db.add(t)
    db.flush()
    return {"id": t.id, "name": t.name}


@router.delete("/templates/{template_id}", status_code=204)
def delete_template(template_id: str, db: Session = Depends(get_db)) -> None:
    t = get_or_404(db, Template, template_id)
    if t.is_builtin:
        raise HTTPException(422, "built-in templates cannot be deleted")
    soft_delete(db, t)


@router.post("/templates/{template_id}/thumbnail")
def template_thumbnail(template_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Render a preview of a template with neutral sample values."""
    from app.services.templates import default_values, fill_template

    t = get_or_404(db, Template, template_id)
    if t.thumbnail_asset_id:
        return {"thumb_url": thumb_url(db.get(Asset, t.thumbnail_asset_id))}
    vals = default_values(None, None, {"headline": "Your headline here", "subheadline": "Supporting line",
                                       "features": ["Feature one", "Feature two", "Feature three", "Feature four"],
                                       "benefits": ["Benefit one", "Benefit two", "Benefit three", "Benefit four"],
                                       "steps": ["Open", "Apply", "Enjoy"]})
    doc = fill_template(t.document, vals, {})
    im = render_document(doc, scale=min(1.0, 480 / max(t.width, t.height)))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    a = create_asset_from_bytes(db, buf.getvalue(), ext="png", source="system", area="thumbs",
                                filename=f"template-{t.id}.png")
    t.thumbnail_asset_id = a.id
    return {"thumb_url": thumb_url(a)}
