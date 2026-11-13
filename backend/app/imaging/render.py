"""Server-side renderer for editor documents (Pillow).

Mirrors the Konva model closely enough for exports from background jobs (factory, A+ ZIP,
listing sets). Rotation is around the layer's top-left (Konva default). Text wraps to the
layer width; long words are broken. Layers render in array order (first = bottom).
"""
from __future__ import annotations

import io
import math
from typing import Any

from PIL import Image, ImageDraw, ImageOps

from app.db.models import Asset
from app.db.session import session_scope
from app.imaging.fonts import get_font
from app.imaging.ops import ImageColorRGB
from app.storage.local import get_storage


def _rgba(color: str | None, opacity: float = 1.0) -> tuple[int, int, int, int] | None:
    if not color or color in ("transparent", "none"):
        return None
    c = color.strip()
    if c.startswith("rgba"):
        parts = [p.strip() for p in c[c.find("(") + 1: c.find(")")].split(",")]
        r, g, b = (int(float(x)) for x in parts[:3])
        a = float(parts[3]) if len(parts) > 3 else 1.0
        return r, g, b, int(255 * a * opacity)
    if c.startswith("#") and len(c) == 4:
        c = "#" + "".join(ch * 2 for ch in c[1:])
    r, g, b = ImageColorRGB(c if c.startswith("#") else "#000000")
    return r, g, b, int(255 * opacity)


def _load_asset(asset_id: str | None) -> Image.Image | None:
    if not asset_id:
        return None
    with session_scope() as db:
        a = db.get(Asset, asset_id)
        key = a.storage_key if a else None
    if not key or not get_storage().exists(key):
        return None
    return ImageOps.exif_transpose(Image.open(io.BytesIO(get_storage().read_bytes(key)))).convert("RGBA")


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: Any, max_w: float, spacing: float) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        words = para.split(" ")
        cur = ""
        for word in words:
            trial = f"{cur} {word}".strip()
            if _text_w(draw, trial, font, spacing) <= max_w or not cur:
                if _text_w(draw, trial, font, spacing) > max_w and not cur:
                    # break a single long word
                    chunk = ""
                    for ch in word:
                        if _text_w(draw, chunk + ch, font, spacing) > max_w and chunk:
                            lines.append(chunk)
                            chunk = ch
                        else:
                            chunk += ch
                    cur = chunk
                else:
                    cur = trial
            else:
                lines.append(cur)
                cur = word
        lines.append(cur)
    return lines


def _text_w(draw: ImageDraw.ImageDraw, s: str, font: Any, spacing: float) -> float:
    return draw.textlength(s, font=font) + max(0, len(s) - 1) * spacing


def _layer_image(layer: dict[str, Any]) -> Image.Image | None:
    """Render one layer into its own RGBA tile of size width×height (pre-rotation)."""
    w, h = max(1, int(round(layer.get("width", 1)))), max(1, int(round(layer.get("height", 1))))
    t = layer.get("type")
    op = float(layer.get("opacity", 1))
    tile = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    if t == "rect":
        fill = _rgba(layer.get("fill"), op)
        stroke = _rgba(layer.get("stroke"), op) if layer.get("strokeWidth") else None
        r = int(layer.get("cornerRadius") or 0)
        d.rounded_rectangle((0, 0, w - 1, h - 1), radius=min(r, w // 2, h // 2), fill=fill, outline=stroke,
                            width=int(layer.get("strokeWidth") or 0))
        return tile
    if t == "ellipse":
        fill = _rgba(layer.get("fill"), op)
        stroke = _rgba(layer.get("stroke"), op) if layer.get("strokeWidth") else None
        d.ellipse((0, 0, w - 1, h - 1), fill=fill, outline=stroke, width=int(layer.get("strokeWidth") or 0))
        return tile
    if t == "text":
        size = float(layer.get("fontSize", 32))
        font = get_font(layer.get("fontFamily"), int(size), layer.get("fontStyle", "normal"))
        spacing = float(layer.get("letterSpacing") or 0)
        lh = size * float(layer.get("lineHeight") or 1.2)
        fill = _rgba(layer.get("fill") or "#000000", op)
        lines = _wrap(d, str(layer.get("text", "")), font, w, spacing)
        needed = int(math.ceil(lh * len(lines))) + 4
        if needed > h:  # text grows downward like Konva auto-height
            tile = Image.new("RGBA", (w, needed), (0, 0, 0, 0))
            d = ImageDraw.Draw(tile)
        align = layer.get("align", "left")
        y = 0.0
        for line in lines:
            lw = _text_w(d, line, font, spacing)
            x = 0.0 if align == "left" else ((w - lw) / 2 if align == "center" else w - lw)
            if spacing:
                for ch in line:
                    d.text((x, y + (lh - size) / 2), ch, font=font, fill=fill)
                    x += d.textlength(ch, font=font) + spacing
            else:
                d.text((x, y + (lh - size) / 2), line, font=font, fill=fill)
            y += lh
        return tile
    if t == "image":
        src = _load_asset(layer.get("assetId"))
        if src is None:
            return None
        crop = layer.get("crop")
        if crop and crop.get("width") and crop.get("height"):
            src = src.crop((int(crop["x"]), int(crop["y"]), int(crop["x"] + crop["width"]),
                            int(crop["y"] + crop["height"])))
        fit = layer.get("fit", "fill")
        if fit == "cover":
            src = ImageOps.fit(src, (w, h), Image.LANCZOS)
            tile.alpha_composite(src)
        elif fit == "contain":
            s = min(w / src.width, h / src.height)
            sw, sh = max(1, int(src.width * s)), max(1, int(src.height * s))
            tile.alpha_composite(src.resize((sw, sh), Image.LANCZOS), ((w - sw) // 2, (h - sh) // 2))
        else:
            tile.alpha_composite(src.resize((w, h), Image.LANCZOS))
        if op < 1:
            a = tile.getchannel("A").point(lambda v: int(v * op))
            tile.putalpha(a)
        return tile
    return None


def render_document(doc: dict[str, Any], *, scale: float = 1.0, transparent: bool = False) -> Image.Image:
    W, H = int(doc["width"]), int(doc["height"])
    bg = None if transparent else _rgba(doc.get("background") or "#ffffff")
    canvas = Image.new("RGBA", (W, H), bg or (0, 0, 0, 0))
    for layer in doc.get("layers", []):
        if not layer.get("visible", True) or layer.get("type") == "group":
            continue
        if layer.get("type") == "line":
            pts = layer.get("points") or []
            stroke = _rgba(layer.get("stroke") or "#000000", float(layer.get("opacity", 1)))
            if len(pts) >= 4 and stroke:
                ox, oy = float(layer.get("x", 0)), float(layer.get("y", 0))
                xy = [(ox + pts[i], oy + pts[i + 1]) for i in range(0, len(pts) - 1, 2)]
                overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                ImageDraw.Draw(overlay).line(xy, fill=stroke, width=max(1, int(layer.get("strokeWidth", 2))))
                canvas.alpha_composite(overlay)
            continue
        tile = _layer_image(layer)
        if tile is None:
            continue
        x, y = float(layer.get("x", 0)), float(layer.get("y", 0))
        rot = float(layer.get("rotation", 0) or 0)
        if rot:
            # Konva rotates clockwise around (x, y); PIL rotates counter-clockwise around center.
            rad = math.radians(rot)
            rotated = tile.rotate(-rot, resample=Image.BICUBIC, expand=True)
            w, h = tile.size
            corners = [(0, 0), (w, 0), (0, h), (w, h)]
            rc = [(cx * math.cos(rad) - cy * math.sin(rad), cx * math.sin(rad) + cy * math.cos(rad)) for cx, cy in corners]
            minx, miny = min(c[0] for c in rc), min(c[1] for c in rc)
            _paste_clipped(canvas, rotated, int(round(x + minx)), int(round(y + miny)))
        else:
            _paste_clipped(canvas, tile, int(round(x)), int(round(y)))
    if scale != 1.0:
        canvas = canvas.resize((max(1, int(W * scale)), max(1, int(H * scale))), Image.LANCZOS)
    return canvas


def _paste_clipped(canvas: Image.Image, tile: Image.Image, x: int, y: int) -> None:
    """alpha_composite requires the tile to fit; crop it to the canvas first."""
    left, top = max(0, -x), max(0, -y)
    right = min(tile.width, canvas.width - x)
    bottom = min(tile.height, canvas.height - y)
    if right <= left or bottom <= top:
        return
    canvas.alpha_composite(tile.crop((left, top, right, bottom)), (x + left, y + top))


def render_png(doc: dict[str, Any], **kw: Any) -> bytes:
    im = render_document(doc, **kw)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()
