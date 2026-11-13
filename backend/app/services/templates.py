"""Built-in editable templates and the template-filling engine.

Editor document JSON (shared with the frontend Konva editor):
    {"width": int, "height": int, "background": "#hex",
     "layers": [{"id", "type": "text|rect|ellipse|image|line|group", "name", "x", "y", "width", "height",
                 "rotation", "opacity", "locked", "visible", "parentId"?, ...type-specific props}]}
Text:   text, fontFamily, fontSize, fontStyle ("normal"|"bold"|"italic"|"bold italic"), fill, align,
        lineHeight, letterSpacing, verticalAlign
Shapes: fill, stroke, strokeWidth, cornerRadius
Image:  assetId, crop?, placeholder? ("product_cutout" | "background" | "product_image")
Line:   points [x1,y1,x2,y2...], stroke, strokeWidth, dash?

Placeholders in strings: {{product_name}}, {{headline}}, {{subheadline}}, {{benefit_1..6}},
{{feature_1..6}}, {{brand_name}}, {{cta}}, {{dim_w}}, {{dim_h}}, {{step_1..3}}, and colors
{{primary}}, {{accent}}, {{ink}}, {{paper}}; font {{font}}, {{font_display}}.
"""
from __future__ import annotations

import copy
import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Template

_PH = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")


def _id() -> str:
    return uuid.uuid4().hex[:12]


def T(name: str, x: float, y: float, w: float, text: str, size: int, *, h: float | None = None,
      bold: bool = False, fill: str = "{{ink}}", align: str = "left", font: str = "{{font}}",
      line_height: float = 1.2, letter: float = 0) -> dict[str, Any]:
    return {"id": _id(), "type": "text", "name": name, "x": x, "y": y, "width": w, "height": h or size * 1.4,
            "rotation": 0, "opacity": 1, "locked": False, "visible": True, "text": text, "fontFamily": font,
            "fontSize": size, "fontStyle": "bold" if bold else "normal", "fill": fill, "align": align,
            "lineHeight": line_height, "letterSpacing": letter, "verticalAlign": "top"}


def R(name: str, x: float, y: float, w: float, h: float, fill: str, *, radius: float = 0, stroke: str | None = None,
      stroke_w: float = 0, opacity: float = 1) -> dict[str, Any]:
    return {"id": _id(), "type": "rect", "name": name, "x": x, "y": y, "width": w, "height": h, "rotation": 0,
            "opacity": opacity, "locked": False, "visible": True, "fill": fill, "stroke": stroke or "",
            "strokeWidth": stroke_w, "cornerRadius": radius}


def E(name: str, x: float, y: float, w: float, h: float, fill: str, *, opacity: float = 1) -> dict[str, Any]:
    return {"id": _id(), "type": "ellipse", "name": name, "x": x, "y": y, "width": w, "height": h, "rotation": 0,
            "opacity": opacity, "locked": False, "visible": True, "fill": fill, "stroke": "", "strokeWidth": 0}


def IMG(name: str, x: float, y: float, w: float, h: float, placeholder: str, *, fit: str = "contain") -> dict[str, Any]:
    return {"id": _id(), "type": "image", "name": name, "x": x, "y": y, "width": w, "height": h, "rotation": 0,
            "opacity": 1, "locked": False, "visible": True, "assetId": None, "placeholder": placeholder, "fit": fit}


def L(name: str, points: list[float], stroke: str = "{{ink}}", width: float = 4, dash: list[float] | None = None) -> dict[str, Any]:
    xs, ys = points[0::2], points[1::2]
    return {"id": _id(), "type": "line", "name": name, "x": 0, "y": 0, "width": max(xs) - min(xs) or 1,
            "height": max(ys) - min(ys) or 1, "rotation": 0, "opacity": 1, "locked": False, "visible": True,
            "points": points, "stroke": stroke, "strokeWidth": width, "dash": dash or []}


def _doc(w: int, h: int, bg: str, layers: list[dict[str, Any]]) -> dict[str, Any]:
    return {"width": w, "height": h, "background": bg, "layers": layers}


def _feature_callouts() -> dict[str, Any]:
    layers: list[dict[str, Any]] = [
        R("Backdrop", 0, 0, 2000, 2000, "{{paper}}"),
        E("Glow", 120, 420, 1100, 1100, "{{primary}}", opacity=0.08),
        IMG("Product", 140, 380, 1000, 1200, "product_cutout"),
        T("Headline", 120, 120, 1760, "{{headline}}", 104, bold=True, font="{{font_display}}", line_height=1.05),
    ]
    for i in range(4):
        y = 520 + i * 300
        layers += [
            R(f"Benefit {i + 1} card", 1180, y, 700, 240, "#ffffff", radius=28, stroke="{{primary}}", stroke_w=3),
            E(f"Benefit {i + 1} dot", 1215, y + 40, 56, 56, "{{primary}}"),
            T(f"Benefit {i + 1}", 1300, y + 36, 550, f"{{{{benefit_{i + 1}}}}}", 46, h=170, line_height=1.25),
        ]
    return _doc(2000, 2000, "#ffffff", layers)


def _lifestyle_headline() -> dict[str, Any]:
    return _doc(2000, 2000, "#ffffff", [
        IMG("Scene", 0, 0, 2000, 2000, "background", fit="cover"),
        R("Top shade", 0, 0, 2000, 520, "#000000", opacity=0.28),
        T("Headline", 120, 120, 1760, "{{headline}}", 120, bold=True, fill="#ffffff", align="center",
          font="{{font_display}}", line_height=1.05),
        T("Subheadline", 220, 300, 1560, "{{subheadline}}", 56, fill="#ffffff", align="center"),
    ])


def _comparison() -> dict[str, Any]:
    layers: list[dict[str, Any]] = [
        R("Backdrop", 0, 0, 2000, 2000, "{{paper}}"),
        T("Headline", 120, 100, 1760, "{{headline}}", 96, bold=True, align="center", font="{{font_display}}"),
        R("Ours column", 760, 300, 520, 1560, "{{primary}}", radius=36, opacity=0.1),
        IMG("Product", 800, 330, 440, 380, "product_cutout"),
        T("Ours label", 760, 730, 520, "{{brand_name}}", 52, bold=True, align="center", fill="{{primary}}"),
        T("Others label", 1320, 730, 560, "Typical alternative", 48, bold=True, align="center", fill="#6b7280"),
    ]
    for i in range(6):
        y = 860 + i * 160
        layers += [
            R(f"Row {i + 1} line", 120, y + 140, 1760, 2, "#d6d3d1"),
            T(f"Row {i + 1} label", 120, y + 40, 620, f"{{{{feature_{i + 1}}}}}", 46, h=110),
            T(f"Row {i + 1} ours", 760, y + 30, 520, "✓", 72, bold=True, align="center", fill="{{primary}}"),
            T(f"Row {i + 1} theirs", 1320, y + 30, 560, "—", 72, align="center", fill="#9ca3af"),
        ]
    return _doc(2000, 2000, "#ffffff", layers)


def _dimensions() -> dict[str, Any]:
    return _doc(2000, 2000, "#ffffff", [
        R("Backdrop", 0, 0, 2000, 2000, "#ffffff"),
        T("Headline", 120, 100, 1760, "Size & dimensions", 96, bold=True, align="center", font="{{font_display}}"),
        IMG("Product", 400, 420, 1200, 1200, "product_cutout"),
        L("Width line", [400, 1720, 1600, 1720], width=6),
        L("Width cap L", [400, 1690, 400, 1750], width=6),
        L("Width cap R", [1600, 1690, 1600, 1750], width=6),
        T("Width label", 700, 1760, 600, "{{dim_w}}", 64, bold=True, align="center"),
        L("Height line", [1720, 420, 1720, 1620], width=6),
        L("Height cap T", [1690, 420, 1750, 420], width=6),
        L("Height cap B", [1690, 1620, 1750, 1620], width=6),
        T("Height label", 1760, 960, 220, "{{dim_h}}", 60, bold=True),
    ])


def _steps() -> dict[str, Any]:
    layers: list[dict[str, Any]] = [
        R("Backdrop", 0, 0, 2000, 2000, "{{paper}}"),
        T("Headline", 120, 100, 1760, "How to use", 104, bold=True, align="center", font="{{font_display}}"),
    ]
    for i in range(3):
        x = 100 + i * 620
        layers += [
            R(f"Step {i + 1} card", x, 360, 560, 1440, "#ffffff", radius=36),
            E(f"Step {i + 1} badge", x + 210, 410, 140, 140, "{{primary}}"),
            T(f"Step {i + 1} number", x + 210, 440, 140, str(i + 1), 72, bold=True, align="center", fill="#ffffff"),
            IMG(f"Step {i + 1} image", x + 40, 600, 480, 700, "product_image"),
            T(f"Step {i + 1} text", x + 40, 1340, 480, f"{{{{step_{i + 1}}}}}", 46, h=400, align="center", line_height=1.3),
        ]
    return _doc(2000, 2000, "#ffffff", layers)


def _aplus_hero() -> dict[str, Any]:
    return _doc(1464, 600, "#ffffff", [
        IMG("Scene", 0, 0, 1464, 600, "background", fit="cover"),
        R("Text panel", 0, 0, 640, 600, "{{paper}}", opacity=0.92),
        T("Headline", 60, 150, 540, "{{headline}}", 54, bold=True, font="{{font_display}}", line_height=1.1, h=200),
        T("Subheadline", 60, 380, 520, "{{subheadline}}", 26, h=160, line_height=1.35),
    ])


def _aplus_feature_row() -> dict[str, Any]:
    layers: list[dict[str, Any]] = [R("Backdrop", 0, 0, 1464, 600, "{{paper}}")]
    for i in range(4):
        x = 36 + i * 357
        layers += [
            R(f"Card {i + 1}", x, 36, 335, 528, "#ffffff", radius=20),
            IMG(f"Image {i + 1}", x + 20, 56, 295, 260, "product_image"),
            T(f"Title {i + 1}", x + 20, 336, 295, f"{{{{feature_{i + 1}}}}}", 26, bold=True, h=80),
            T(f"Body {i + 1}", x + 20, 420, 295, f"{{{{benefit_{i + 1}}}}}", 20, h=130, line_height=1.35),
        ]
    return _doc(1464, 600, "#ffffff", layers)


def _social_promo() -> dict[str, Any]:
    return _doc(1080, 1350, "#ffffff", [
        R("Backdrop", 0, 0, 1080, 1350, "{{primary}}"),
        E("Halo", 140, 300, 800, 800, "#ffffff", opacity=0.14),
        IMG("Product", 190, 330, 700, 720, "product_cutout"),
        T("Headline", 80, 90, 920, "{{headline}}", 76, bold=True, fill="#ffffff", align="center",
          font="{{font_display}}", line_height=1.05, h=200),
        R("CTA pill", 340, 1150, 400, 100, "#ffffff", radius=50),
        T("CTA", 340, 1176, 400, "{{cta}}", 40, bold=True, align="center", fill="{{primary}}"),
    ])


def _sponsored_brand() -> dict[str, Any]:
    return _doc(1200, 628, "#ffffff", [
        IMG("Scene", 0, 0, 1200, 628, "background", fit="cover"),
        R("Text panel", 660, 0, 540, 628, "{{paper}}", opacity=0.94),
        IMG("Product", 60, 64, 560, 500, "product_cutout"),
        T("Headline", 700, 170, 460, "{{headline}}", 50, bold=True, font="{{font_display}}", h=200, line_height=1.1),
        T("Subheadline", 700, 390, 460, "{{subheadline}}", 26, h=140, line_height=1.35),
    ])


BUILTIN: list[tuple[str, str, Any]] = [
    ("Feature callouts", "infographic", _feature_callouts),
    ("Lifestyle + headline", "lifestyle", _lifestyle_headline),
    ("Comparison table", "comparison", _comparison),
    ("Size & dimensions", "infographic", _dimensions),
    ("3-step how-to", "infographic", _steps),
    ("A+ hero banner", "aplus", _aplus_hero),
    ("A+ four features", "aplus", _aplus_feature_row),
    ("Social promo 4:5", "social", _social_promo),
    ("Sponsored Brand image", "ad", _sponsored_brand),
]


def seed_builtin_templates(db: Session) -> None:
    existing = {t.name for t in db.scalars(select(Template).where(Template.is_builtin.is_(True)))}
    for name, cat, fn in BUILTIN:
        if name in existing:
            continue
        doc = fn()
        db.add(Template(name=name, category=cat, width=doc["width"], height=doc["height"], document=doc,
                        is_builtin=True))


def builtin_document(name: str) -> dict[str, Any]:
    for n, _cat, fn in BUILTIN:
        if n == name:
            return fn()
    raise KeyError(name)


def fill_template(doc: dict[str, Any], values: dict[str, str], images: dict[str, str | None]) -> dict[str, Any]:
    """Return a new document with placeholders replaced.

    `values` maps placeholder names to text/colors; `images` maps placeholder kinds
    ('product_cutout', 'background', 'product_image') to asset IDs (product_image may be
    a comma-separated list consumed in order). Empty text layers left after filling are hidden.
    """
    out = copy.deepcopy(doc)
    queue = [a for a in (images.get("product_image") or "").split(",") if a]

    def sub(s: str) -> str:
        return _PH.sub(lambda m: values.get(m.group(1), ""), s)

    for layer in out["layers"]:
        layer["id"] = _id()
        # Remember the placeholder version so the design can be re-filled for another product later.
        if isinstance(layer.get("text"), str) and _PH.search(layer["text"]) and "template_text" not in layer:
            layer["template_text"] = layer["text"]
        for key in ("text", "fill", "stroke", "fontFamily"):
            if isinstance(layer.get(key), str):
                layer[key] = sub(layer[key])
        if layer["type"] == "text" and not layer["text"].strip():
            layer["visible"] = False
        if layer["type"] == "image" and layer.get("placeholder"):
            ph = layer["placeholder"]
            if ph == "product_image":
                layer["assetId"] = queue.pop(0) if queue else images.get("product_cutout")
            else:
                layer["assetId"] = images.get(ph)
    if isinstance(out.get("background"), str):
        out["background"] = sub(out["background"]) or "#ffffff"
    return out


def default_values(product: Any | None, brand: Any | None, copy_: dict[str, Any] | None = None) -> dict[str, str]:
    copy_ = copy_ or {}
    colors = (brand.colors if brand and brand.colors else []) + ["#0f766e", "#7c3aed"]
    feats = list(copy_.get("features") or (product.features if product else []) or [])
    bens = list(copy_.get("benefits") or (product.benefits if product else []) or [])
    specs = (product.specifications if product else {}) or {}
    vals: dict[str, str] = {
        "product_name": product.name if product else "Your product",
        "brand_name": brand.name if brand else (product.name if product else "Our pick"),
        "headline": copy_.get("headline") or (product.name if product else "Your headline"),
        "subheadline": copy_.get("subheadline") or ((product.description or "")[:120] if product else ""),
        "cta": copy_.get("cta") or "Shop now",
        "primary": colors[0], "accent": colors[1] if len(colors) > 1 else colors[0],
        "ink": "#1c1917", "paper": "#f6f4f1",
        "font": (brand.secondary_font or brand.primary_font) if brand and (brand.secondary_font or brand.primary_font) else "Inter",
        "font_display": brand.primary_font if brand and brand.primary_font else "Inter",
        "dim_w": str(specs.get("Width") or specs.get("width") or copy_.get("dim_w") or "W"),
        "dim_h": str(specs.get("Height") or specs.get("height") or copy_.get("dim_h") or "H"),
    }
    for i in range(6):
        vals[f"feature_{i + 1}"] = str(feats[i]) if i < len(feats) else ""
        vals[f"benefit_{i + 1}"] = str(bens[i]) if i < len(bens) else (str(feats[i]) if i < len(feats) else "")
    for i, s in enumerate((copy_.get("steps") or [])[:3]):
        vals[f"step_{i + 1}"] = str(s)
    return vals
