"""Reference-guided creative ("Inspire").

We analyze a reference creative for *design principles* — palette, layout grid, text hierarchy,
subject placement — and build a NEW editable layout with the user's own product, brand and copy.
We never copy the reference's pixels, text, logos or brand identity into the output.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.ai import fallback_manager as fm
from app.ai.base import NoProviderAvailable, TextRequest
from app.db.models import Asset, Brand, Product
from app.imaging import ops
from app.imaging.render import render_png
from app.services.assets import create_asset_from_bytes, load_image
from app.services.creative import _doc_to_db, generate_background, get_or_make_cutout, main_product_asset
from app.services.templates import IMG, R, T, E, default_values, fill_template


def analyze_reference(db: Session, asset_id: str, *, use_vision: bool = True) -> dict[str, Any]:
    a = db.get(Asset, asset_id)
    if a is None or a.kind != "image":
        raise ValueError("reference image not found")
    im = load_image(a)
    analysis = {"palette": ops.extract_palette(im, 6), "layout": ops.analyze_layout(im), "vision": None}
    if use_vision:
        try:
            small = im.convert("RGB")
            small.thumbnail((768, 768))
            db.commit()  # don't hold a write lock during the vision call
            res = fm.generate_text(TextRequest(
                prompt=("Describe the DESIGN of this marketing image for a designer (not its brand or exact words). "
                        "Return JSON: {\"composition\": \"...\", \"mood\": \"...\", \"typography\": \"...\", "
                        "\"text_hierarchy\": [\"headline role\", ...], \"background\": \"...\", "
                        "\"design_principles\": [\"...\"]}"),
                images=[ops.to_png(small)], json_mode=True, temperature=0.3, max_tokens=700),
                purpose="inspire_vision")
            v = res.json()
            if isinstance(v, dict):
                analysis["vision"] = {**v, "provider": res.provider, "model": res.model}
        except (NoProviderAvailable, ValueError):
            analysis["vision"] = None
    a.meta = {**(a.meta or {}), "inspire_analysis": analysis}
    return analysis


def _layout_doc(analysis: dict[str, Any], w: int, h: int) -> dict[str, Any]:
    """Build an original layout that follows the reference's structure."""
    lay = analysis["layout"]
    pal = [c["hex"] for c in analysis["palette"]]
    placement = lay.get("subject_placement", "center")
    text_side = lay.get("text_side") or ("left" if placement == "right" else ("right" if placement == "left" else "top"))
    blocks = lay.get("text_blocks") or []
    layers: list[dict[str, Any]] = [IMG("Scene", 0, 0, w, h, "background", fit="cover")]
    if text_side in ("left", "right"):
        px = 0 if text_side == "left" else w * 0.52
        layers.append(R("Text panel", px, 0, w * 0.48, h, pal[0] if pal else "#f5f5f4", opacity=0.9))
        tx, tw = px + w * 0.05, w * 0.38
        layers.append(T("Headline", tx, h * 0.22, tw, "{{headline}}", int(h * 0.075), bold=True,
                        font="{{font_display}}", fill="{{ink}}", h=h * 0.3, line_height=1.08))
        layers.append(T("Subheadline", tx, h * 0.55, tw, "{{subheadline}}", int(h * 0.033), h=h * 0.2, line_height=1.35))
        ix = w * 0.06 if text_side == "right" else w * 0.54
        layers.append(IMG("Product", ix, h * 0.12, w * 0.4, h * 0.76, "product_cutout"))
    else:
        layers.append(R("Top band", 0, 0, w, h * 0.3, pal[0] if pal else "#f5f5f4", opacity=0.85))
        layers.append(T("Headline", w * 0.06, h * 0.06, w * 0.88, "{{headline}}", int(h * 0.07), bold=True,
                        font="{{font_display}}", align="center", h=h * 0.2, line_height=1.08))
        layers.append(IMG("Product", w * 0.2, h * 0.32, w * 0.6, h * 0.62, "product_cutout"))
    if len(blocks) >= 3:  # reference used supporting callouts → add benefit chips
        for i in range(min(3, len(blocks) - 1)):
            y = h * (0.7 + i * 0.085)
            x = w * 0.06 if text_side != "left" else w * 0.55
            if text_side in ("left", "right"):
                x = (0 if text_side == "left" else w * 0.52) + w * 0.05
                y = h * (0.74 + i * 0.075)
            layers.append(E(f"Chip {i + 1} dot", x, y + h * 0.008, h * 0.03, h * 0.03, "{{primary}}"))
            layers.append(T(f"Benefit {i + 1}", x + h * 0.045, y, w * 0.36, f"{{{{benefit_{i + 1}}}}}", int(h * 0.028)))
    return {"width": w, "height": h, "background": pal[-1] if pal else "#ffffff", "layers": layers}


def generate_from_reference(db: Session, p: dict[str, Any], progress: Any = None) -> dict[str, Any]:
    tick = progress or (lambda *_a, **_k: None)
    ref = db.get(Asset, p["reference_asset_id"])
    if ref is None:
        raise ValueError("reference not found")
    analysis = (ref.meta or {}).get("inspire_analysis") or analyze_reference(db, ref.id, use_vision=False)
    product = db.get(Product, p["product_id"]) if p.get("product_id") else None
    if product is None:
        raise ValueError("choose a product")
    brand = db.get(Brand, p.get("brand_id") or product.brand_id or "") if (p.get("brand_id") or product.brand_id) else None
    w, h = int(p.get("width") or analysis["layout"]["size"][0]), int(p.get("height") or analysis["layout"]["size"][1])
    scale = 2000 / max(w, h)
    w, h = int(w * scale), int(h * scale)
    src = main_product_asset(db, product)
    cutout = get_or_make_cutout(db, product, src) if src else None
    db.commit()  # release the write lock before the (slow) AI background call
    tick(0.3, "Generating background in the reference's mood")
    vision = analysis.get("vision") or {}
    mood = ", ".join(x for x in (vision.get("mood"), vision.get("background")) if x)
    pal = ", ".join(c["hex"] for c in analysis["palette"][:3])
    prompt = (f"product photography backdrop, {mood or 'clean modern'}, color palette {pal}, "
              "empty space for a product, no text, no logos, no products")
    bg, prov = generate_background(prompt, w, h, provider=p.get("provider"), seed=p.get("seed"),
                                   fallback_colors=(analysis["palette"][0]["hex"], analysis["palette"][-1]["hex"]))
    bg_asset = create_asset_from_bytes(db, ops.to_png(bg), ext="png", source="generated", filename="inspire-bg.png",
                                       title=f"{product.name} — inspired background", product_id=product.id,
                                       provider=prov["provider"], model=prov["model"], is_ai_generated=bool(prov["ai"]),
                                       meta={"prompt": prompt, "creative_type": "background"})
    tick(0.7, "Composing layout")
    values = default_values(product, brand, p.get("copy") or {})
    doc = fill_template(_layout_doc(analysis, w, h), values,
                        {"background": bg_asset.id, "product_cutout": cutout.id if cutout else None})
    d = _doc_to_db(db, doc, f"Inspired — {product.name}", p.get("project_id"))
    png = render_png(doc)
    a = create_asset_from_bytes(db, png, ext="png", source="generated", filename=f"inspired-{product.name}.png",
                                title=f"Inspired — {product.name}", product_id=product.id, provider=prov["provider"],
                                model=prov["model"], is_ai_generated=bool(prov["ai"]),
                                meta={"operation": "inspire", "document_id": d.id, "reference_asset_id": ref.id,
                                      "note": "Layout follows the reference's composition; content, text and "
                                              "imagery are your own."})
    d.thumbnail_asset_id = a.id
    return {"asset_ids": [a.id], "document_id": d.id, "provenance": prov}
