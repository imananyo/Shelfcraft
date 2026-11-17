"""A+ Content builder: module library, ordering, editable modules (each is an editor document), export."""
from __future__ import annotations

import io
import json
import zipfile
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.models import Brand, EditorDocument, ExportRecord, Product, Project
from app.db.session import get_db
from app.imaging.render import render_document
from app.routers.common import get_or_404, soft_delete
from app.routers.editor import doc_summary
from app.services.documents import create_document, document_json
from app.services.templates import IMG, E, R, T, builtin_document, default_values, fill_template

router = APIRouter(prefix="/aplus", tags=["aplus"])

# Dimensions commonly documented for A+ modules — shown with a "verify in A+ Content Manager" note.
MODULE_TYPES: dict[str, dict[str, Any]] = {
    "hero_banner": {"label": "Hero banner", "basic": [970, 600], "premium": [1464, 600], "mobile": [600, 450]},
    "feature_row": {"label": "Four features", "basic": [970, 400], "premium": [1464, 600], "mobile": [600, 450]},
    "brand_story": {"label": "Brand story", "basic": [970, 300], "premium": [1464, 600], "mobile": [600, 450]},
    "comparison": {"label": "Comparison table", "basic": [970, 600], "premium": [1464, 800], "mobile": [600, 700]},
    "lifestyle": {"label": "Lifestyle image + text", "basic": [970, 600], "premium": [1464, 600], "mobile": [600, 450]},
    "detail": {"label": "Product detail close-up", "basic": [970, 600], "premium": [1464, 600], "mobile": [600, 450]},
    # One continuous design, exported as consecutive slices so the modules join without seams.
    "seamless": {"label": "Seamless story (one continuous image)", "basic": [970, 1800], "premium": [1464, 1800],
                 "mobile": [600, 1350], "slice": {"basic": 600, "premium": 600, "mobile": 450}},
}
DIMENSION_NOTE = "Sizes are commonly documented A+ module sizes. Verify in Amazon's A+ Content Manager before upload."


def _module_doc(kind: str, w: int, h: int) -> dict[str, Any]:
    if kind == "hero_banner" and (w, h) == (1464, 600):
        return builtin_document("A+ hero banner")
    if kind == "feature_row" and (w, h) == (1464, 600):
        return builtin_document("A+ four features")
    s = h / 600
    if kind == "brand_story":
        return {"width": w, "height": h, "background": "{{paper}}", "layers": [
            R("Accent bar", 0, 0, w * 0.012, h, "{{primary}}"),
            IMG("Logo / product", w * 0.05, h * 0.15, h * 0.7, h * 0.7, "product_cutout"),
            T("Headline", w * 0.05 + h * 0.8, h * 0.18, w * 0.55, "Our story", int(46 * s), bold=True, font="{{font_display}}"),
            T("Story", w * 0.05 + h * 0.8, h * 0.18 + 70 * s, w * 0.55, "{{subheadline}}", int(24 * s), h=h * 0.55, line_height=1.45),
        ]}
    if kind == "comparison":
        base = builtin_document("Comparison table")
        sx, sy = w / base["width"], h / base["height"]
        for layer in base["layers"]:
            layer["x"], layer["y"] = layer["x"] * sx, layer["y"] * sy
            layer["width"], layer["height"] = layer["width"] * sx, layer["height"] * sy
            if "fontSize" in layer:
                layer["fontSize"] = max(12, layer["fontSize"] * min(sx, sy))
            if layer["type"] == "line":
                layer["points"] = [v * (sx if i % 2 == 0 else sy) for i, v in enumerate(layer["points"])]
        base["width"], base["height"] = w, h
        return base
    if kind == "seamless":
        band = h / 3
        layers: list[dict[str, Any]] = [
            IMG("Continuous scene", 0, 0, w, h, "background", fit="cover"),
            R("Top wash", 0, 0, w, band * 0.9, "{{paper}}", opacity=0.82),
            T("Headline", w * 0.06, band * 0.22, w * 0.6, "{{headline}}", int(band * 0.12), bold=True, font="{{font_display}}", h=band * 0.3, line_height=1.08),
            T("Subheadline", w * 0.06, band * 0.58, w * 0.55, "{{subheadline}}", int(band * 0.05), h=band * 0.25, line_height=1.35),
            IMG("Product", w * 0.58, band * 0.55, w * 0.38, band * 1.1, "product_cutout"),
            R("Feature band", 0, band * 1.75, w, band * 0.85, "{{paper}}", opacity=0.9),
        ]
        for i in range(3):
            x = w * (0.06 + i * 0.31)
            layers += [E(f"Feature {i + 1} dot", x, band * 1.88, band * 0.09, band * 0.09, "{{primary}}"),
                       T(f"Feature {i + 1}", x, band * 2.02, w * 0.27, f"{{{{feature_{i + 1}}}}}", int(band * 0.055), bold=True, h=band * 0.16),
                       T(f"Benefit {i + 1}", x, band * 2.2, w * 0.27, f"{{{{benefit_{i + 1}}}}}", int(band * 0.04), h=band * 0.3, line_height=1.35)]
        layers.append(T("Sign-off", w * 0.06, band * 2.7, w * 0.88, "{{brand_name}}", int(band * 0.07), bold=True, align="center",
                        font="{{font_display}}", fill="#ffffff"))
        return {"width": w, "height": h, "background": "#ffffff", "layers": layers}
    if kind == "detail":
        return {"width": w, "height": h, "background": "#ffffff", "layers": [
            IMG("Detail image", 0, 0, w * 0.6, h, "product_image", fit="cover"),
            T("Headline", w * 0.64, h * 0.25, w * 0.32, "{{feature_1}}", int(40 * s), bold=True, font="{{font_display}}", h=h * 0.25),
            T("Body", w * 0.64, h * 0.5, w * 0.32, "{{benefit_1}}", int(22 * s), h=h * 0.4, line_height=1.45),
        ]}
    # lifestyle (and fallback for other sizes)
    return {"width": w, "height": h, "background": "#ffffff", "layers": [
        IMG("Scene", 0, 0, w, h, "background", fit="cover"),
        R("Caption panel", w * 0.05, h * 0.62, w * 0.5, h * 0.3, "{{paper}}", radius=int(16 * s), opacity=0.92),
        T("Headline", w * 0.08, h * 0.66, w * 0.44, "{{headline}}", int(36 * s), bold=True, font="{{font_display}}", h=h * 0.1),
        T("Body", w * 0.08, h * 0.66 + 52 * s, w * 0.44, "{{subheadline}}", int(20 * s), h=h * 0.14, line_height=1.35),
    ]}


@router.get("/modules")
def module_library() -> dict[str, Any]:
    return {"modules": MODULE_TYPES, "note": DIMENSION_NOTE}


class AplusIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    product_id: str | None = None
    brand_id: str | None = None
    tier: str = Field(default="premium", pattern="^(basic|premium|mobile)$")
    modules: list[str] = Field(default_factory=lambda: ["hero_banner", "feature_row", "brand_story"], max_length=7)


def aplus_out(db: Session, p: Project) -> dict[str, Any]:
    data = p.data or {}
    mods = []
    for m in data.get("modules", []):
        d = db.get(EditorDocument, m["document_id"])
        if d is None or d.deleted_at:
            continue
        mods.append({**m, "document": doc_summary(db, d), "label": MODULE_TYPES.get(m["type"], {}).get("label", m["type"])})
    return {"id": p.id, "name": p.name, "product_id": p.product_id, "brand_id": p.brand_id, "tier": data.get("tier"),
            "modules": mods, "note": DIMENSION_NOTE, "updated_at": p.updated_at}


def _add_module(db: Session, p: Project, kind: str) -> dict[str, Any]:
    if kind not in MODULE_TYPES:
        raise HTTPException(422, f"unknown module {kind}")
    tier = (p.data or {}).get("tier", "premium")
    w, h = MODULE_TYPES[kind][tier]
    product = db.get(Product, p.product_id) if p.product_id else None
    brand = db.get(Brand, p.brand_id) if p.brand_id else None
    imgs: dict[str, str | None] = {}
    if product:
        from app.services.creative import get_or_make_cutout, main_product_asset

        src = main_product_asset(db, product)
        if src:
            try:
                imgs["product_cutout"] = get_or_make_cutout(db, product, src).id
            except Exception:  # noqa: BLE001 - cutout is a nicety; fall back to the raw photo
                imgs["product_cutout"] = src.id
            imgs["background"] = src.id
        imgs["product_image"] = ",".join(pi.asset_id for pi in product.images if pi.role != "cutout")
    copy_ = (p.data or {}).get("copy") or {}
    doc = fill_template(_module_doc(kind, w, h), default_values(product, brand, copy_), imgs)
    d = create_document(db, name=f"{p.name} — {MODULE_TYPES[kind]['label']}", doc=doc, project_id=p.id)
    return {"type": kind, "document_id": d.id}


@router.get("")
def list_aplus(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    from sqlalchemy import select

    rows = db.scalars(select(Project).where(Project.kind == "aplus", Project.deleted_at.is_(None))
                      .order_by(Project.updated_at.desc())).all()
    return [{"id": p.id, "name": p.name, "tier": (p.data or {}).get("tier"),
             "module_count": len((p.data or {}).get("modules", [])), "updated_at": p.updated_at} for p in rows]


@router.post("", status_code=201)
def create_aplus(body: AplusIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    product = get_or_404(db, Product, body.product_id) if body.product_id else None
    p = Project(kind="aplus", name=body.name, product_id=body.product_id,
                brand_id=body.brand_id or (product.brand_id if product else None), data={"tier": body.tier, "modules": []})
    db.add(p)
    db.flush()
    p.data = {**p.data, "modules": [_add_module(db, p, m) for m in body.modules]}
    return aplus_out(db, p)


@router.get("/{project_id}")
def get_aplus(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return aplus_out(db, get_or_404(db, Project, project_id))


@router.post("/{project_id}/modules", status_code=201)
def add_module(project_id: str, body: dict[str, str], db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, Project, project_id)
    mods = list((p.data or {}).get("modules", []))
    if len(mods) >= 7:
        raise HTTPException(422, "A+ layouts support up to 7 modules")
    mods.append(_add_module(db, p, body.get("type", "")))
    p.data = {**(p.data or {}), "modules": mods}
    return aplus_out(db, p)


@router.put("/{project_id}/order")
def reorder(project_id: str, body: dict[str, list[str]], db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, Project, project_id)
    mods = {m["document_id"]: m for m in (p.data or {}).get("modules", [])}
    order = [mods[i] for i in body.get("document_ids", []) if i in mods]
    order += [m for k, m in mods.items() if m not in order]
    p.data = {**(p.data or {}), "modules": order}
    return aplus_out(db, p)


@router.delete("/{project_id}/modules/{document_id}")
def remove_module(project_id: str, document_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = get_or_404(db, Project, project_id)
    p.data = {**(p.data or {}), "modules": [m for m in (p.data or {}).get("modules", []) if m["document_id"] != document_id]}
    d = db.get(EditorDocument, document_id)
    if d:
        soft_delete(db, d)
    return aplus_out(db, p)


def _carry_edits(src: dict[str, Any], dst: dict[str, Any]) -> dict[str, Any]:
    """Copy the user's edits (text, colors, fonts, swapped images) from a desktop module onto the mobile layout,
    matching layers by name. Geometry stays mobile-native."""
    by_name = {ly.get("name"): ly for ly in src.get("layers", []) if ly.get("name")}
    for ly in dst.get("layers", []):
        old = by_name.get(ly.get("name"))
        if not old or old.get("type") != ly.get("type"):
            continue
        if ly["type"] == "text":
            for k in ("text", "fill", "fontFamily", "fontStyle", "align"):
                if k in old:
                    ly[k] = old[k]
        elif ly["type"] == "image" and old.get("assetId"):
            ly["assetId"] = old["assetId"]
        elif ly["type"] in ("rect", "ellipse"):
            for k in ("fill", "stroke", "opacity"):
                if k in old:
                    ly[k] = old[k]
        ly["visible"] = old.get("visible", True)
    if src.get("background") and not str(src["background"]).startswith("{{"):
        dst["background"] = src["background"]
    return dst


@router.post("/{project_id}/convert-mobile", status_code=201)
def convert_to_mobile(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Make a Premium-mobile copy of a desktop A+ project, keeping your edited copy and images."""
    src = get_or_404(db, Project, project_id)
    if (src.data or {}).get("tier") == "mobile":
        raise HTTPException(422, "this A+ project is already the mobile version")
    p = Project(kind="aplus", name=f"{src.name} (mobile)"[:200], product_id=src.product_id, brand_id=src.brand_id,
                data={"tier": "mobile", "modules": [], "converted_from": src.id})
    db.add(p)
    db.flush()
    mods = []
    for m in (src.data or {}).get("modules", []):
        old = db.get(EditorDocument, m["document_id"])
        if old is None or old.deleted_at or m["type"] not in MODULE_TYPES:
            continue
        new = _add_module(db, p, m["type"])
        d = db.get(EditorDocument, new["document_id"])
        doc = _carry_edits(document_json(old), document_json(d))
        from app.services.documents import save_document

        save_document(db, d, doc, base_version=None, revision=False)
        mods.append(new)
    p.data = {**p.data, "modules": mods}
    return aplus_out(db, p)


@router.delete("/{project_id}", status_code=204)
def delete_aplus(project_id: str, db: Session = Depends(get_db)) -> None:
    soft_delete(db, get_or_404(db, Project, project_id))


@router.get("/{project_id}/preview.png")
def preview(project_id: str, db: Session = Depends(get_db)) -> StreamingResponse:
    """Stacked preview of all modules, as they would appear on a product page."""
    from PIL import Image

    p = get_or_404(db, Project, project_id)
    ims = []
    for m in (p.data or {}).get("modules", []):
        d = db.get(EditorDocument, m["document_id"])
        if d and not d.deleted_at:
            ims.append(render_document(document_json(d)))
    if not ims:
        raise HTTPException(422, "add modules first")
    width = max(i.width for i in ims)
    sheet = Image.new("RGB", (width, sum(i.height for i in ims) + 16 * (len(ims) - 1)), "#ffffff")
    y = 0
    for i in ims:
        sheet.paste(i.convert("RGB"), ((width - i.width) // 2, y))
        y += i.height + 16
    scale = min(1.0, 1000 / width)
    sheet = sheet.resize((int(sheet.width * scale), int(sheet.height * scale)))
    buf = io.BytesIO()
    sheet.save(buf, "PNG")
    return StreamingResponse(iter([buf.getvalue()]), media_type="image/png")


@router.post("/{project_id}/export.zip")
def export_zip(project_id: str, db: Session = Depends(get_db)) -> StreamingResponse:
    p = get_or_404(db, Project, project_id)
    buf = io.BytesIO()
    manifest = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for i, m in enumerate((p.data or {}).get("modules", []), 1):
            d = db.get(EditorDocument, m["document_id"])
            if d is None or d.deleted_at:
                continue
            doc = document_json(d)
            im = render_document(doc).convert("RGB")
            texts = [layer.get("text") for layer in doc["layers"] if layer["type"] == "text" and layer.get("visible", True)]
            if m["type"] == "seamless":
                # Slice the continuous design into consecutive modules (uploaded in order, they join seamlessly).
                step = MODULE_TYPES["seamless"]["slice"].get((p.data or {}).get("tier", "premium"), 600)
                for k, top in enumerate(range(0, im.height, step)):
                    part = im.crop((0, top, im.width, min(im.height, top + step)))
                    b = io.BytesIO()
                    part.save(b, "JPEG", quality=92, optimize=True)
                    fname = f"{i:02d}{chr(97 + k)}-seamless-{part.width}x{part.height}.jpg"
                    z.writestr(fname, b.getvalue())
                    manifest.append({"order": f"{i}{chr(97 + k)}", "module": "seamless slice", "file": fname, "size": [part.width, part.height],
                                     "bytes": len(b.getvalue()), "text": [t for t in texts if t] if k == 0 else []})
                continue
            b = io.BytesIO()
            im.save(b, "JPEG", quality=92, optimize=True)
            fname = f"{i:02d}-{m['type']}-{im.width}x{im.height}.jpg"
            z.writestr(fname, b.getvalue())
            manifest.append({"order": i, "module": m["type"], "file": fname, "size": [im.width, im.height],
                             "bytes": len(b.getvalue()), "text": [t for t in texts if t]})
        z.writestr("modules.json", json.dumps({"project": p.name, "tier": (p.data or {}).get("tier"),
                                               "note": DIMENSION_NOTE, "modules": manifest}, indent=2, ensure_ascii=False))
    db.add(ExportRecord(kind="zip", source_type="aplus", source_id=p.id, params={"modules": len(manifest)}))
    safe = "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in p.name)[:80]
    return StreamingResponse(iter([buf.getvalue()]), media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{safe}-aplus.zip"'})
