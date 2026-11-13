"""Creative generation pipeline.

Principle: the product must not be altered without consent. When a product photo exists we
(1) cut it out locally with rembg, (2) generate or build a background, (3) composite the
untouched cutout. Optional "harmonize" runs a light img2img pass that MAY alter product
details — it is opt-in and labeled. Text never comes from the image model: text-heavy
creatives are editor documents rendered with real fonts.
"""
from __future__ import annotations

import logging
from typing import Any

from PIL import Image
from sqlalchemy.orm import Session

from app.ai import fallback_manager as fm
from app.ai.base import ImageRequest, NoProviderAvailable
from app.db.models import Asset, Brand, EditorDocument, EditorLayer, Product, ProductImage, Project, Template
from app.imaging import ops
from app.imaging.render import render_png
from app.services.assets import create_asset_from_bytes, load_image
from app.services.copywriting import NEGATIVE, creative_prompt
from app.services.templates import builtin_document, default_values, fill_template

log = logging.getLogger("shelfcraft.creative")

CREATIVE_TYPES: dict[str, dict[str, Any]] = {
    "white_bg_main": {"label": "White-background main image", "mode": "cutout_white"},
    "hero": {"label": "Premium hero image", "mode": "composite"},
    "lifestyle": {"label": "Lifestyle image", "mode": "composite"},
    "studio": {"label": "Studio photography", "mode": "composite"},
    "detail": {"label": "Product detail image", "mode": "composite"},
    "promo": {"label": "Promotional image", "mode": "template", "template": "Social promo 4:5"},
    "social": {"label": "Social media creative", "mode": "template", "template": "Social promo 4:5"},
    "feature": {"label": "Feature callouts", "mode": "template", "template": "Feature callouts"},
    "infographic": {"label": "Benefit infographic", "mode": "template", "template": "Feature callouts"},
    "comparison": {"label": "Comparison chart", "mode": "template", "template": "Comparison table"},
    "dimensions": {"label": "Dimensions graphic", "mode": "template", "template": "Size & dimensions"},
    "steps": {"label": "Step-by-step usage", "mode": "template", "template": "3-step how-to"},
    "lifestyle_headline": {"label": "Lifestyle + headline", "mode": "template", "template": "Lifestyle + headline"},
    "ad_sb": {"label": "Sponsored Brand image", "mode": "template", "template": "Sponsored Brand image"},
}

SLOT_TO_TYPE = {"main_white": "white_bg_main", "lifestyle": "lifestyle", "lifestyle_2": "hero",
                "infographic_features": "feature", "infographic_benefits": "lifestyle_headline",
                "comparison": "comparison", "dimensions": "dimensions", "detail": "detail"}


def main_product_asset(db: Session, product: Product | None) -> Asset | None:
    if product is None:
        return None
    for pi in sorted(product.images, key=lambda i: i.position):
        if pi.role != "cutout" and pi.asset and not pi.asset.deleted_at:
            return pi.asset
    return None


def get_or_make_cutout(db: Session, product: Product, source: Asset) -> Asset:
    """Cache one rembg cutout per source photo (stored as a ProductImage with role 'cutout')."""
    for pi in product.images:
        if pi.role == "cutout" and pi.asset and (pi.asset.meta or {}).get("parent_asset_id") == source.id:
            return pi.asset
    cut = ops.remove_background(load_image(source))
    asset = create_asset_from_bytes(db, ops.to_png(ops.trim_transparent(cut, pad=4)), ext="png", source="edited",
                                    filename=f"{product.name}-cutout.png", product_id=product.id,
                                    brand_id=product.brand_id, provider="rembg", model="u2net (local)",
                                    is_ai_generated=True, title=f"{product.name} — cutout",
                                    meta={"operation": "remove_background", "parent_asset_id": source.id})
    db.add(ProductImage(product_id=product.id, asset_id=asset.id, role="cutout", position=999))
    db.flush()
    return asset


def generate_background(prompt: str, w: int, h: int, *, provider: str | None, seed: int | None,
                        fallback_colors: tuple[str, str]) -> tuple[Image.Image, dict[str, Any]]:
    """AI background if any free/local image provider works; otherwise a labeled non-AI gradient."""
    try:
        res = fm.generate_image(ImageRequest(prompt=prompt, negative_prompt=NEGATIVE, width=w, height=h, seed=seed),
                                purpose="background", preferred=provider)
        bg = ops.cover_resize(ops.from_bytes(res.image_png).convert("RGB"), w, h)
        bg, cleaned = ops.clean_text_artifacts(bg)
        prov: dict[str, Any] = {"provider": res.provider, "model": res.model, "ai": True, "seed": res.seed}
        if cleaned:
            prov["text_artifacts_removed"] = cleaned
        return bg, prov
    except NoProviderAvailable as e:
        log.info("no image provider; using gradient backdrop (%s)", e)
        return ops.studio_gradient(w, h, *fallback_colors), {
            "provider": "shelfcraft", "model": "gradient backdrop (non-AI)", "ai": False,
            "note": "No image-generation provider was available, so a plain gradient backdrop was used.",
        }


def _doc_to_db(db: Session, doc: dict[str, Any], name: str, project_id: str | None) -> EditorDocument:
    d = EditorDocument(name=name[:200], width=doc["width"], height=doc["height"],
                       background=doc.get("background", "#ffffff"), project_id=project_id)
    db.add(d)
    db.flush()
    for z, layer in enumerate(doc["layers"]):
        props = {k: v for k, v in layer.items() if k not in ("id", "type", "name", "locked", "visible", "parentId")}
        db.add(EditorLayer(id=layer["id"], document_id=d.id, type=layer["type"], name=layer.get("name", layer["type"]),
                           z_index=z, parent_id=layer.get("parentId"), locked=bool(layer.get("locked")),
                           visible=bool(layer.get("visible", True)), props=props))
    db.flush()
    return d


def generate_creative(db: Session, *, product_id: str | None, brand_id: str | None, creative_type: str,
                      width: int, height: int, style: str = "minimal", prompt_override: str | None = None,
                      extra_prompt: str = "", provider: str | None = None, seed: int | None = None,
                      harmonize: bool = False, copy: dict[str, Any] | None = None, project_id: str | None = None,
                      template_id: str | None = None, progress: Any = None) -> dict[str, Any]:
    spec = CREATIVE_TYPES.get(creative_type)
    if spec is None:
        raise ValueError(f"unknown creative type {creative_type}")
    product = db.get(Product, product_id) if product_id else None
    brand = db.get(Brand, brand_id) if brand_id else (db.get(Brand, product.brand_id) if product and product.brand_id else None)
    src = main_product_asset(db, product)
    colors = (brand.colors if brand and brand.colors else []) + ["#f5f5f4", "#e7e5e4"]
    tick = progress or (lambda *_a, **_k: None)
    name = f"{spec['label']} — {product.name if product else 'untitled'}"
    common = dict(product_id=product.id if product else None, brand_id=brand.id if brand else None, project_id=project_id)

    cutout = None
    if src is not None and spec["mode"] in ("cutout_white", "composite", "template"):
        tick(0.15, "Removing background (local AI)")
        cutout = get_or_make_cutout(db, product, src)  # type: ignore[arg-type]
        # Release SQLite's single write lock before slow AI calls so the rest of the app can save.
        db.commit()

    # ---- white background main image
    if spec["mode"] == "cutout_white":
        if cutout is None:
            raise ValueError("A product photo is required for a white-background main image.")
        size = max(width, height)
        im = ops.white_background(load_image(cutout), size=size)
        if (width, height) != (size, size):
            im = ops.cover_resize(im, width, height)
        asset = create_asset_from_bytes(db, ops.to_png(im), ext="png", source="generated", filename=f"{name}.png",
                                        title=name, provider="rembg", model="u2net (local) + white composite",
                                        is_ai_generated=True, meta={"creative_type": creative_type,
                                        "operation": "white_background", "parent_asset_id": src.id if src else None,
                                        "note": "Product pixels are from your photo; only the background was removed."},
                                        **common)
        return {"asset_ids": [asset.id], "document_id": None, "provenance": {"provider": "rembg", "ai": True}}

    # ---- composite: AI background + untouched product
    if spec["mode"] == "composite":
        prompt = prompt_override or creative_prompt(product, brand, creative_type, style, extra_prompt,
                                                    background_only=cutout is not None)
        tick(0.3, "Generating background")
        if cutout is None:
            # No photo: full text-to-image. The product's look is invented → flagged clearly.
            res = fm.generate_image(ImageRequest(prompt=prompt, negative_prompt=NEGATIVE, width=width, height=height,
                                                 seed=seed), purpose=creative_type, preferred=provider)
            im = ops.cover_resize(ops.from_bytes(res.image_png).convert("RGB"), width, height)
            asset = create_asset_from_bytes(db, ops.to_png(im), ext="png", source="generated", filename=f"{name}.png",
                                            title=name, provider=res.provider, model=res.model, is_ai_generated=True,
                                            meta={"creative_type": creative_type, "prompt": prompt, "seed": res.seed,
                                                  "style": style, "note": "No product photo: the product shown is "
                                                  "AI-imagined and will not match your real product."}, **common)
            return {"asset_ids": [asset.id], "document_id": None,
                    "provenance": {"provider": res.provider, "model": res.model, "ai": True}}
        bg, prov = generate_background(prompt, width, height, provider=provider, seed=seed,
                                       fallback_colors=(colors[0] if creative_type == "promo" else "#f5f5f4", "#d6d3d1"))
        tick(0.75, "Compositing your product")
        # Per-type placement: products sit on the lower third (where generated surfaces usually are).
        scale, anchor = {"detail": (0.82, (0.5, 0.52)), "hero": (0.55, (0.5, 0.55)), "lifestyle": (0.42, (0.5, 0.64)),
                         "studio": (0.58, (0.5, 0.58))}.get(creative_type, (0.55, (0.5, 0.58)))
        comp = ops.composite_product(bg, load_image(cutout), scale=scale, anchor=anchor)
        meta = {"creative_type": creative_type, "prompt": prompt, "style": style, "seed": prov.get("seed"),
                "background_provider": prov["provider"], "background_model": prov["model"],
                "parent_asset_id": src.id if src else None, "operation": "composite",
                "text_artifacts_removed": prov.get("text_artifacts_removed", 0),
                "note": prov.get("note") or "Background generated; product pixels are from your photo."}
        out_provider, out_model = prov["provider"], prov["model"]
        if harmonize and prov["ai"]:
            db.commit()
            tick(0.85, "Harmonizing lighting (may alter product details)")
            res = fm.generate_image(ImageRequest(prompt=prompt.replace("no products, ", ""), width=width, height=height,
                                                 init_image=ops.to_png(comp.convert("RGB")), strength=0.3, seed=seed),
                                    purpose="harmonize", preferred=provider)
            comp = ops.cover_resize(ops.from_bytes(res.image_png).convert("RGB"), width, height)
            meta["note"] = "Harmonized with img2img — product details may differ slightly from your photo."
            out_provider, out_model = res.provider, res.model
        asset = create_asset_from_bytes(db, ops.to_png(comp.convert("RGB")), ext="png", source="generated",
                                        filename=f"{name}.png", title=name, provider=out_provider, model=out_model,
                                        is_ai_generated=bool(prov["ai"]), meta=meta, **common)
        # Also save the layered version so it stays editable.
        doc = {"width": width, "height": height, "background": "#ffffff", "layers": []}
        bg_asset = create_asset_from_bytes(db, ops.to_png(bg), ext="png", source="generated",
                                           filename=f"{name}-background.png", title=f"{name} — background",
                                           provider=prov["provider"], model=prov["model"], is_ai_generated=bool(prov["ai"]),
                                           meta={"creative_type": "background", "prompt": prompt}, **common)
        filled = fill_template({"width": width, "height": height, "background": "#ffffff", "layers": [
            {"id": "bg", "type": "image", "name": "Background", "x": 0, "y": 0, "width": width, "height": height,
             "rotation": 0, "opacity": 1, "locked": True, "visible": True, "placeholder": "background", "fit": "cover"},
            {"id": "pr", "type": "image", "name": "Product", "x": width * (1 - scale) / 2, "y": height * anchor[1] - height * scale / 2,
             "width": width * scale, "height": height * scale, "rotation": 0, "opacity": 1, "locked": False,
             "visible": True, "placeholder": "product_cutout", "fit": "contain"}]},
            {}, {"background": bg_asset.id, "product_cutout": cutout.id})
        d = _doc_to_db(db, filled, name, project_id)
        asset.meta = {**meta, "document_id": d.id}
        return {"asset_ids": [asset.id], "document_id": d.id,
                "provenance": {"provider": out_provider, "model": out_model, "ai": bool(prov["ai"])}}

    # ---- template-based (text rendered with real fonts, not by the model)
    if template_id:
        t = db.get(Template, template_id)
        base = t.document if t else builtin_document(spec["template"])
    else:
        base = builtin_document(spec["template"])
    needs_bg = any(layer.get("placeholder") == "background" for layer in base["layers"])
    images: dict[str, str | None] = {"product_cutout": cutout.id if cutout else None}
    prov: dict[str, Any] = {"provider": "shelfcraft", "model": "template renderer", "ai": False}
    if needs_bg:
        tick(0.35, "Generating background")
        bw, bh = base["width"], base["height"]
        prompt = prompt_override or creative_prompt(product, brand, "lifestyle", style, extra_prompt, background_only=True)
        bg, prov = generate_background(prompt, bw, bh, provider=provider, seed=seed, fallback_colors=("#e7e5e4", "#a8a29e"))
        if cutout is not None:
            bg = ops.composite_product(bg, load_image(cutout), scale=0.5, anchor=(0.5, 0.62)).convert("RGB")
        bg_asset = create_asset_from_bytes(db, ops.to_png(bg), ext="png", source="generated",
                                           filename=f"{name}-scene.png", title=f"{name} — scene",
                                           provider=prov["provider"], model=prov["model"], is_ai_generated=bool(prov["ai"]),
                                           meta={"creative_type": "background", "prompt": prompt}, **common)
        images["background"] = bg_asset.id
    others = [pi.asset_id for pi in (product.images if product else []) if pi.role != "cutout"]
    images["product_image"] = ",".join(others[:6])
    tick(0.7, "Laying out text with your brand fonts")
    # Templates have native sizes (e.g. 2000×2000); the editor can resize the canvas afterwards.
    doc = fill_template(base, default_values(product, brand, copy), images)
    d = _doc_to_db(db, doc, name, project_id)
    png = render_png(doc)
    asset = create_asset_from_bytes(db, png, ext="png", source="generated", filename=f"{name}.png", title=name,
                                    provider=prov["provider"], model=prov["model"], is_ai_generated=bool(prov["ai"]),
                                    meta={"creative_type": creative_type, "document_id": d.id, "operation": "template",
                                          "template": spec["template"], "note": prov.get("note") or
                                          "Text is rendered as editable layers, not generated by an image model."},
                                    **common)
    d.thumbnail_asset_id = asset.id
    return {"asset_ids": [asset.id], "document_id": d.id, "provenance": prov}


def ensure_project(db: Session, *, kind: str, name: str, product_id: str | None, brand_id: str | None,
                   project_id: str | None = None) -> Project:
    if project_id:
        p = db.get(Project, project_id)
        if p:
            return p
    p = Project(kind=kind, name=name[:200], product_id=product_id, brand_id=brand_id, data={})
    db.add(p)
    db.flush()
    return p
