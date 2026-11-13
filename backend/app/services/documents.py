"""Editor document persistence: snapshot ↔ normalized layer rows, optimistic versioning, revisions."""
from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import EditorDocument, EditorLayer, EditorRevision

MAX_LAYERS = 400
MAX_REVISIONS = 30
_CORE = {"id", "type", "name", "locked", "visible", "parentId"}
ALLOWED_TYPES = {"text", "rect", "ellipse", "image", "line", "group"}


class VersionConflict(Exception):
    def __init__(self, current: int) -> None:
        super().__init__(f"document changed elsewhere (server version {current})")
        self.current = current


def document_json(d: EditorDocument) -> dict[str, Any]:
    layers = []
    for layer in sorted(d.layers, key=lambda r: r.z_index):
        layers.append({"id": layer.id, "type": layer.type, "name": layer.name, "locked": layer.locked,
                       "visible": layer.visible, **({"parentId": layer.parent_id} if layer.parent_id else {}),
                       **(layer.props or {})})
    return {"width": d.width, "height": d.height, "background": d.background, "layers": layers}


def validate_doc(doc: dict[str, Any]) -> None:
    w, h = int(doc.get("width", 0)), int(doc.get("height", 0))
    if not (16 <= w <= 8000 and 16 <= h <= 8000):
        raise ValueError("canvas size must be between 16 and 8000 px")
    layers = doc.get("layers") or []
    if len(layers) > MAX_LAYERS:
        raise ValueError(f"at most {MAX_LAYERS} layers")
    seen: set[str] = set()
    for layer in layers:
        if layer.get("type") not in ALLOWED_TYPES:
            raise ValueError(f"unsupported layer type {layer.get('type')}")
        lid = str(layer.get("id") or "")
        if not lid or len(lid) > 32 or lid in seen:
            raise ValueError("every layer needs a unique id (≤32 chars)")
        seen.add(lid)


def save_document(db: Session, d: EditorDocument, doc: dict[str, Any], *, base_version: int | None,
                  revision: bool = False) -> EditorDocument:
    if base_version is not None and base_version != d.version:
        raise VersionConflict(d.version)
    validate_doc(doc)
    if revision:
        db.add(EditorRevision(document_id=d.id, version=d.version, snapshot=document_json(d)))
        old = db.scalars(select(EditorRevision.id).where(EditorRevision.document_id == d.id)
                         .order_by(EditorRevision.created_at.desc()).offset(MAX_REVISIONS)).all()
        if old:
            db.execute(delete(EditorRevision).where(EditorRevision.id.in_(old)))
    d.width, d.height = int(doc["width"]), int(doc["height"])
    d.background = str(doc.get("background") or "#ffffff")[:40]
    db.execute(delete(EditorLayer).where(EditorLayer.document_id == d.id))
    db.flush()
    db.expire(d, ["layers"])
    for z, layer in enumerate(doc.get("layers") or []):
        props = {k: v for k, v in layer.items() if k not in _CORE}
        db.add(EditorLayer(id=str(layer["id"]), document_id=d.id, type=layer["type"],
                           name=str(layer.get("name") or layer["type"])[:120], z_index=z,
                           parent_id=layer.get("parentId"), locked=bool(layer.get("locked")),
                           visible=bool(layer.get("visible", True)), props=props))
    d.version += 1
    db.flush()
    db.refresh(d)
    return d


def create_document(db: Session, *, name: str, doc: dict[str, Any], project_id: str | None = None) -> EditorDocument:
    validate_doc(doc)
    d = EditorDocument(name=name[:200], width=int(doc["width"]), height=int(doc["height"]),
                       background=str(doc.get("background") or "#ffffff"), project_id=project_id, version=0)
    db.add(d)
    db.flush()
    return save_document(db, d, doc, base_version=None)
