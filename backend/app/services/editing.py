"""Spot edit / AI image editing. Each operation declares whether it used AI and which model."""
from __future__ import annotations

import base64
import io
from typing import Any

from PIL import Image, ImageFilter
from sqlalchemy.orm import Session

from app.ai import fallback_manager as fm
from app.ai.base import ImageRequest
from app.db.models import Asset
from app.imaging import inpaint, ops
from app.services.assets import create_asset_from_bytes, load_image

OPERATIONS: dict[str, dict[str, Any]] = {
    "remove_background": {"label": "Remove background", "ai": True, "needs_mask": False},
    "replace_background": {"label": "Replace background", "ai": True, "needs_mask": False},
    "remove_object": {"label": "Remove object", "ai": True, "needs_mask": True},
    "generative_fill": {"label": "Replace object (generative fill)", "ai": True, "needs_mask": True},
    "extend": {"label": "Extend image", "ai": True, "needs_mask": False},
    "enhance": {"label": "Enhance (auto contrast, sharpen)", "ai": False, "needs_mask": False},
    "upscale": {"label": "Upscale 2× (Lanczos)", "ai": False, "needs_mask": False},
    "recolor": {"label": "Recolor (hue shift)", "ai": False, "needs_mask": False},
}


def decode_mask(data_url: str | None, size: tuple[int, int]) -> Image.Image | None:
    """Mask arrives from the browser as a PNG data URL: painted (opaque/white) pixels = edit area."""
    if not data_url:
        return None
    raw = base64.b64decode(data_url.split(",", 1)[-1])
    if len(raw) > 20 * 1024 * 1024:
        raise ValueError("mask too large")
    m = Image.open(io.BytesIO(raw))
    if m.mode in ("RGBA", "LA"):
        m = m.getchannel("A")
    else:
        m = m.convert("L")
    m = m.resize(size, Image.NEAREST).point(lambda v: 255 if v > 20 else 0)
    if m.getbbox() is None:
        raise ValueError("the mask is empty — paint over the area to edit")
    return m


def run_edit(db: Session, p: dict[str, Any], progress: Any = None) -> dict[str, Any]:
    tick = progress or (lambda *_a, **_k: None)
    op = p["operation"]
    if op not in OPERATIONS:
        raise ValueError(f"unknown operation {op}")
    src = db.get(Asset, p["asset_id"])
    if src is None or src.kind != "image":
        raise ValueError("source image not found")
    im = load_image(src)
    mask = decode_mask(p.get("mask"), im.size)
    if OPERATIONS[op]["needs_mask"] and mask is None:
        raise ValueError("this operation needs a painted mask")
    provider, model, ai_used, note = "shelfcraft", "", OPERATIONS[op]["ai"], ""
    tick(0.15, OPERATIONS[op]["label"])

    if op == "remove_background":
        out = ops.remove_background(im)
        provider, model = "rembg", "u2net (local)"
    elif op == "replace_background":
        cut = ops.remove_background(im)
        mode = p.get("background_mode", "color")
        if mode == "color":
            bg = Image.new("RGB", im.size, p.get("color") or "#ffffff")
            provider, model, ai_used, note = "rembg", "u2net (local) + solid color", True, "Background removed with AI; color fill is non-AI."
        elif mode == "asset":
            bga = db.get(Asset, p.get("background_asset_id") or "")
            if bga is None:
                raise ValueError("background image not found")
            bg = ops.cover_resize(load_image(bga).convert("RGB"), *im.size)
            provider, model = "rembg", "u2net (local) + your image"
        else:
            tick(0.4, "Generating new background")
            res = fm.generate_image(ImageRequest(prompt=(p.get("prompt") or "clean studio background") +
                                                 ", empty, no products, no text", width=im.width, height=im.height),
                                    purpose="replace_background", preferred=p.get("provider"))
            bg = ops.cover_resize(ops.from_bytes(res.image_png).convert("RGB"), *im.size)
            provider, model = res.provider, f"{res.model} + rembg u2net"
        out = Image.new("RGBA", im.size)
        out.paste(bg, (0, 0))
        out.alpha_composite(cut)
        out = out.convert("RGB")
    elif op == "remove_object":
        assert mask is not None
        if p.get("engine") != "opencv":
            try:
                tick(0.3, "Removing object with LaMa (first run downloads ~200 MB)")
                out = inpaint.inpaint_lama(im, mask)
                provider, model = "lama", "big-lama ONNX (local)"
            except Exception as e:  # noqa: BLE001 - fall back to non-AI and say so
                out = inpaint.inpaint_opencv(im, mask)
                provider, model, ai_used = "opencv", "Telea inpaint (non-AI)", False
                note = f"LaMa unavailable ({type(e).__name__}); used classical inpainting instead."
        else:
            out = inpaint.inpaint_opencv(im, mask)
            provider, model, ai_used = "opencv", "Telea inpaint (non-AI)", False
    elif op == "generative_fill":
        assert mask is not None
        prompt = (p.get("prompt") or "").strip()
        if not prompt:
            raise ValueError("describe what should appear in the masked area")
        tick(0.25, "Clearing masked area")
        try:
            base = inpaint.inpaint_lama(im, mask)
        except Exception:  # noqa: BLE001
            base = inpaint.inpaint_opencv(im, mask)
        bbox = mask.getbbox()
        assert bbox is not None
        pad = int(max(bbox[2] - bbox[0], bbox[3] - bbox[1]) * 0.35) + 16
        box = (max(0, bbox[0] - pad), max(0, bbox[1] - pad), min(im.width, bbox[2] + pad), min(im.height, bbox[3] + pad))
        crop = base.convert("RGB").crop(box)
        tick(0.5, "Generating content (img2img)")
        res = fm.generate_image(ImageRequest(prompt=prompt + ", photorealistic, seamless, matching lighting",
                                             width=crop.width, height=crop.height, init_image=ops.to_png(crop),
                                             strength=float(p.get("strength", 0.75))),
                                purpose="generative_fill", preferred=p.get("provider"))
        gen = ops.from_bytes(res.image_png).convert("RGB").resize(crop.size, Image.LANCZOS)
        m_crop = mask.crop(box).filter(ImageFilter.GaussianBlur(6))
        merged = Image.composite(gen, crop, m_crop)
        out = base.convert("RGB")
        out.paste(merged, box[:2])
        provider, model = res.provider, f"{res.model} img2img + LaMa"
        note = "Experimental: free/local models have no true inpainting model here; results vary."
    elif op == "extend":
        w, h = int(p.get("width") or im.width), int(p.get("height") or im.height)
        if w < im.width and h < im.height:
            raise ValueError("target size must be larger than the image in at least one dimension")
        canvas, new_area = ops.extend_canvas(im, max(w, 64), max(h, 64))
        try:
            tick(0.4, "Filling new area with LaMa")
            out = inpaint.inpaint_lama(canvas, new_area)
            provider, model = "lama", "big-lama ONNX outpaint (local)"
            note = "LaMa fills extended areas with plausible texture; best for plain or repetitive backgrounds."
        except Exception as e:  # noqa: BLE001
            out, provider, model, ai_used = canvas, "shelfcraft", "blurred extension (non-AI)", False
            note = f"AI fill unavailable ({type(e).__name__}); used blurred extension."
    elif op == "enhance":
        out = ops.enhance(im, sharpen=float(p.get("sharpen", 1.25)), saturation=float(p.get("saturation", 1.08)),
                          brightness=float(p.get("brightness", 1.0)), denoise=bool(p.get("denoise")))
        model = "auto-contrast + sharpen (non-AI)"
    elif op == "upscale":
        if im.width * im.height > 16_000_000:
            raise ValueError("image already very large")
        out = ops.upscale(im, float(p.get("factor", 2.0)))
        model = "Lanczos upscale (non-AI)"
    else:  # recolor
        out = ops.recolor(im, p.get("color") or "#ff0000", mask=mask, strength=float(p.get("strength", 0.85)))
        model = "hue shift (non-AI)"

    tick(0.9, "Saving")
    asset = create_asset_from_bytes(
        db, ops.to_png(out), ext="png", source="edited", filename=f"{src.title or src.filename}-{op}.png",
        title=f"{(src.title or src.filename).rsplit('.', 1)[0]} — {OPERATIONS[op]['label']}",
        product_id=src.product_id, brand_id=src.brand_id, project_id=src.project_id, provider=provider, model=model,
        is_ai_generated=ai_used, folder_id=src.folder_id,
        meta={"operation": op, "parent_asset_id": src.id, "prompt": p.get("prompt"), "note": note})
    return {"asset_id": asset.id, "parent_asset_id": src.id, "provider": provider, "model": model, "ai": ai_used,
            "note": note}
