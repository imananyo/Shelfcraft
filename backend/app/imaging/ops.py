"""Image operations: background removal (AI), compositing, enhancement (non-AI), palette, layout analysis."""
from __future__ import annotations

import io
import logging
import threading
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from app.config import get_settings

log = logging.getLogger("shelfcraft.imaging")
_rembg_session = None
_rembg_lock = threading.Lock()
REMBG_MODEL = "u2net"  # MIT-licensed U²-Net; ~170 MB, downloaded once to data/models/rembg


def to_png(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def from_bytes(data: bytes) -> Image.Image:
    return ImageOps.exif_transpose(Image.open(io.BytesIO(data)))


# ---------------------------------------------------------------- AI: background removal
def remove_background(im: Image.Image) -> Image.Image:
    """Return RGBA cutout using rembg (U²-Net, local ONNX)."""
    global _rembg_session
    import os

    os.environ.setdefault("U2NET_HOME", str(get_settings().models_dir / "rembg"))
    from rembg import new_session, remove

    with _rembg_lock:
        if _rembg_session is None:
            _rembg_session = new_session(REMBG_MODEL)
        out = remove(im.convert("RGB"), session=_rembg_session, post_process_mask=True)
    assert isinstance(out, Image.Image)
    return out.convert("RGBA")


def trim_transparent(im: Image.Image, pad: int = 0) -> Image.Image:
    bbox = im.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
    if not bbox:
        return im
    l, t, r, b = bbox
    return im.crop((max(0, l - pad), max(0, t - pad), min(im.width, r + pad), min(im.height, b + pad)))


# ---------------------------------------------------------------- compositing (non-AI)
def fit_size(w: int, h: int, max_w: int, max_h: int) -> tuple[int, int]:
    s = min(max_w / w, max_h / h)
    return max(1, int(w * s)), max(1, int(h * s))


def contact_shadow(cutout: Image.Image, strength: float = 0.35, blur: int = 18) -> Image.Image:
    """Soft elliptical ground shadow sized to the product footprint."""
    w, h = cutout.size
    eh = max(8, h // 7)
    pad = blur * 3  # room for the blur to fall off to zero → no visible tile edges
    sh = Image.new("L", (w + pad * 2, eh + pad * 2), 0)
    d = ImageDraw.Draw(sh)
    d.ellipse((pad + w * 0.1, pad, pad + w * 0.9, pad + eh), fill=int(255 * strength))
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    shadow = Image.new("RGBA", sh.size, (0, 0, 0, 0))
    shadow.putalpha(sh)
    return shadow


def composite_product(background: Image.Image, cutout: Image.Image, *, scale: float = 0.62,
                      anchor: tuple[float, float] = (0.5, 0.56), shadow: bool = True) -> Image.Image:
    """Place an untouched product cutout onto a background (keeps product pixels exact)."""
    bg = background.convert("RGBA")
    cut = trim_transparent(cutout)
    tw, th = fit_size(cut.width, cut.height, int(bg.width * scale), int(bg.height * scale))
    cut = cut.resize((tw, th), Image.LANCZOS)
    x = int(bg.width * anchor[0] - tw / 2)
    y = int(bg.height * anchor[1] - th / 2)
    if shadow:
        sh = contact_shadow(cut)
        # Centre the padded shadow under the product's base.
        sx = int(x + tw / 2 - sh.width / 2)
        sy = int(y + th - sh.height / 2)
        _alpha_paste(bg, sh, sx, sy)
    _alpha_paste(bg, cut, x, y)
    return bg


def _alpha_paste(base: Image.Image, tile: Image.Image, x: int, y: int) -> None:
    """alpha_composite that tolerates tiles extending past the canvas edges."""
    left, top = max(0, -x), max(0, -y)
    right, bottom = min(tile.width, base.width - x), min(tile.height, base.height - y)
    if right > left and bottom > top:
        base.alpha_composite(tile.crop((left, top, right, bottom)), (x + left, y + top))


def clean_text_artifacts(im: Image.Image, edge: float = 0.18) -> tuple[Image.Image, int]:
    """Remove hallucinated watermark-like text that few-step diffusion models often add near edges.

    Only text-like regions inside the top/bottom `edge` band are considered (the centre is left alone so
    real scene detail isn't touched). Uses LaMa when available; returns (image, regions_removed).
    """
    from app.imaging import inpaint

    if not inpaint.lama_available():
        return im, 0
    lay = analyze_layout(im)
    w, h = im.size
    boxes = [b for b in lay["text_blocks"] if b["y"] > 1 - edge - 0.02 or b["y"] + b["h"] < edge + 0.02]
    if not boxes:
        return im, 0
    mask = Image.new("L", im.size, 0)
    d = ImageDraw.Draw(mask)
    for b in boxes:
        pad_x, pad_y = int(w * 0.015), int(h * 0.015)
        d.rectangle((int(b["x"] * w) - pad_x, int(b["y"] * h) - pad_y, int((b["x"] + b["w"]) * w) + pad_x,
                     int((b["y"] + b["h"]) * h) + pad_y), fill=255)
    try:
        return inpaint.inpaint_lama(im.convert("RGB"), mask), len(boxes)
    except Exception:  # noqa: BLE001 - cleanup is best-effort; never fail a generation over it
        log.warning("text-artifact cleanup failed", exc_info=True)
        return im, 0


def white_background(cutout: Image.Image, size: int = 2000, fill_ratio: float = 0.85) -> Image.Image:
    """Marketplace-style main image: product on pure white, product filling ~85% of frame."""
    cut = trim_transparent(cutout)
    tw, th = fit_size(cut.width, cut.height, int(size * fill_ratio), int(size * fill_ratio))
    cut = cut.resize((tw, th), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    canvas.alpha_composite(cut, ((size - tw) // 2, (size - th) // 2))
    return canvas.convert("RGB")


def studio_gradient(w: int, h: int, top: str, bottom: str) -> Image.Image:
    """Clean seamless-paper style gradient backdrop (non-AI)."""
    t = np.array(ImageColorRGB(top), dtype=np.float32)
    b = np.array(ImageColorRGB(bottom), dtype=np.float32)
    ramp = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    arr = (t * (1 - ramp) + b * ramp).repeat(w, axis=1)
    return Image.fromarray(arr.astype(np.uint8), "RGB")


def ImageColorRGB(hex_color: str) -> tuple[int, int, int]:  # noqa: N802 - mirrors PIL naming
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return (240, 240, 240)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def cover_resize(im: Image.Image, w: int, h: int) -> Image.Image:
    """Resize + center-crop to exactly w×h (like CSS object-fit: cover)."""
    return ImageOps.fit(im, (w, h), Image.LANCZOS, centering=(0.5, 0.5))


def extend_canvas(im: Image.Image, w: int, h: int, mode: str = "blur") -> tuple[Image.Image, Image.Image]:
    """Outpaint helper: place image on a larger canvas; returns (canvas, mask_of_new_area).

    mode 'blur' fills new area with a blurred stretch (non-AI); the mask lets an AI model refine it.
    """
    src = im.convert("RGB")
    sw, sh = fit_size(src.width, src.height, w, h)
    src = src.resize((sw, sh), Image.LANCZOS)
    base = cover_resize(src, w, h).filter(ImageFilter.GaussianBlur(40)) if mode == "blur" else Image.new("RGB", (w, h), "white")
    x, y = (w - sw) // 2, (h - sh) // 2
    base.paste(src, (x, y))
    mask = Image.new("L", (w, h), 255)
    ImageDraw.Draw(mask).rectangle((x + 4, y + 4, x + sw - 5, y + sh - 5), fill=0)
    return base, mask


# ---------------------------------------------------------------- enhancement (non-AI)
def enhance(im: Image.Image, *, auto_contrast: bool = True, sharpen: float = 1.25, saturation: float = 1.08,
            brightness: float = 1.0, denoise: bool = False) -> Image.Image:
    alpha = im.getchannel("A") if im.mode == "RGBA" else None
    rgb = im.convert("RGB")
    if denoise:
        arr = cv2.fastNlMeansDenoisingColored(np.array(rgb), None, 5, 5, 7, 21)
        rgb = Image.fromarray(arr)
    if auto_contrast:
        rgb = ImageOps.autocontrast(rgb, cutoff=0.5)
    rgb = ImageEnhance.Color(rgb).enhance(saturation)
    rgb = ImageEnhance.Brightness(rgb).enhance(brightness)
    rgb = ImageEnhance.Sharpness(rgb).enhance(sharpen)
    if alpha is not None:
        rgb.putalpha(alpha)
    return rgb


def upscale(im: Image.Image, factor: float = 2.0) -> Image.Image:
    """Lanczos upscale + mild unsharp mask (non-AI)."""
    w, h = int(im.width * factor), int(im.height * factor)
    return im.resize((w, h), Image.LANCZOS).filter(ImageFilter.UnsharpMask(radius=1.6, percent=60, threshold=2))


def recolor(im: Image.Image, target_hex: str, mask: Image.Image | None = None, strength: float = 0.85) -> Image.Image:
    """Hue/saturation shift toward a target color (variant swaps). Non-AI, preserves shading."""
    rgba = im.convert("RGBA")
    hsv = cv2.cvtColor(np.array(rgba.convert("RGB")), cv2.COLOR_RGB2HSV).astype(np.float32)
    tr, tg, tb = ImageColorRGB(target_hex)
    t_h, t_s, _ = cv2.cvtColor(np.uint8([[[tr, tg, tb]]]), cv2.COLOR_RGB2HSV)[0, 0].astype(np.float32)
    m = np.ones(hsv.shape[:2], np.float32) if mask is None else (np.array(mask.convert("L").resize(rgba.size)) / 255.0)
    m = m * (np.array(rgba.getchannel("A")) / 255.0) * strength
    hsv[..., 0] = hsv[..., 0] * (1 - m) + t_h * m
    hsv[..., 1] = hsv[..., 1] * (1 - m) + max(t_s, hsv[..., 1].mean()) * m
    out = Image.fromarray(cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB))
    out.putalpha(rgba.getchannel("A"))
    return out


# ---------------------------------------------------------------- analysis
def extract_palette(im: Image.Image, k: int = 6) -> list[dict[str, Any]]:
    from sklearn.cluster import KMeans

    small = im.convert("RGB").copy()
    small.thumbnail((200, 200))
    px = np.array(small).reshape(-1, 3).astype(np.float32)
    k = min(k, max(1, len(np.unique(px, axis=0))))
    km = KMeans(n_clusters=k, n_init=4, random_state=0).fit(px)
    counts = np.bincount(km.labels_, minlength=k)
    order = np.argsort(-counts)
    total = counts.sum()
    out = []
    for i in order:
        r, g, b = (int(c) for c in km.cluster_centers_[i])
        out.append({"hex": f"#{r:02x}{g:02x}{b:02x}", "share": round(float(counts[i] / total), 3)})
    return out


def analyze_layout(im: Image.Image) -> dict[str, Any]:
    """Heuristic composition analysis: text-like regions, focal subject, thirds, symmetry, whitespace."""
    rgb = np.array(im.convert("RGB"))
    h, w = rgb.shape[:2]
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    # Text-like regions: morphological gradient → horizontal closing → contours with text-ish aspect.
    grad = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    _, bw = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    closed = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (max(9, w // 60), 3)))
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    blocks = []
    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        if cw > w * 0.08 and 8 < ch < h * 0.2 and cw / max(ch, 1) > 2.2:
            region = bw[y:y + ch, x:x + cw]
            fill = float(region.mean() / 255)
            if 0.12 < fill < 0.85:
                blocks.append({"x": x / w, "y": y / h, "w": cw / w, "h": ch / h, "height_px": ch})
    blocks.sort(key=lambda b: (-b["height_px"], b["y"]))
    for rank, b in enumerate(blocks[:12]):
        b["role"] = "headline" if rank == 0 else ("subhead" if rank < 3 else "body")
    blocks = sorted(blocks[:12], key=lambda b: b["y"])
    # Focal subject: saliency via spectral residual if available, else edge density.
    try:
        sal = cv2.saliency.StaticSaliencySpectralResidual_create()
        _, smap = sal.computeSaliency(rgb)
        smap = (smap * 255).astype(np.uint8)
    except AttributeError:
        smap = cv2.GaussianBlur(cv2.Canny(gray, 50, 150), (51, 51), 0)
    _, sm = cv2.threshold(smap, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    ys, xs = np.nonzero(sm)
    focal = ({"x": float(xs.mean() / w), "y": float(ys.mean() / h),
              "bbox": [float(xs.min() / w), float(ys.min() / h), float(xs.max() / w), float(ys.max() / h)]}
             if len(xs) else {"x": 0.5, "y": 0.5, "bbox": [0.25, 0.25, 0.75, 0.75]})
    edges = cv2.Canny(gray, 60, 160)
    whitespace = float(1 - (cv2.dilate(edges, np.ones((15, 15), np.uint8)) > 0).mean())
    left, right = gray[:, : w // 2], cv2.flip(gray[:, w - w // 2:], 1)
    symmetry = float(1 - np.abs(left.astype(np.float32) - right.astype(np.float32)).mean() / 255)
    fx = focal["x"]
    placement = "left" if fx < 0.4 else ("right" if fx > 0.6 else "center")
    text_side = None
    if blocks:
        tx = float(np.mean([b["x"] + b["w"] / 2 for b in blocks]))
        text_side = "left" if tx < 0.42 else ("right" if tx > 0.58 else "center")
    return {
        "size": [w, h], "aspect": round(w / h, 3), "text_blocks": blocks, "focal_point": focal,
        "subject_placement": placement, "text_side": text_side, "whitespace_ratio": round(whitespace, 3),
        "symmetry": round(symmetry, 3),
        "grid": "split" if text_side in ("left", "right") and placement != text_side else
                ("centered" if placement == "center" else "rule-of-thirds"),
    }


def diff_preview(before: Image.Image, after: Image.Image) -> float:
    """Fraction of pixels that changed — used in tests and to sanity-check edits."""
    a, b = before.convert("RGB"), after.convert("RGB").resize(before.size)
    d = np.array(ImageChops.difference(a, b).convert("L"))
    return float((d > 12).mean())
