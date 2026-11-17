"""Layered SVG export of an editor document — opens with editable layers in Figma, Illustrator, Inkscape
and Canva (shapes and text stay vector/editable; images are embedded with their crop/fit applied)."""
from __future__ import annotations

import base64
import io
from typing import Any
from xml.sax.saxutils import escape, quoteattr

from PIL import Image, ImageDraw

from app.imaging.fonts import get_font
from app.imaging.render import _layer_image, _wrap


def _color(c: str | None) -> str:
    return c if c else "none"


def _transform(layer: dict[str, Any]) -> str:
    x, y = float(layer.get("x", 0)), float(layer.get("y", 0))
    rot = float(layer.get("rotation", 0) or 0)
    return f"translate({x:.2f} {y:.2f})" + (f" rotate({rot:.2f})" if rot else "")


def _stroke(layer: dict[str, Any]) -> str:
    sw = float(layer.get("strokeWidth") or 0)
    return f' stroke={quoteattr(_color(layer.get("stroke")))} stroke-width="{sw:g}"' if sw and layer.get("stroke") else ""


def document_to_svg(doc: dict[str, Any]) -> str:
    W, H = int(doc["width"]), int(doc["height"])
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{W}" height="{H}" '
           f'viewBox="0 0 {W} {H}">']
    out.append(f'<rect id="Background" width="{W}" height="{H}" fill={quoteattr(doc.get("background") or "#ffffff")}/>')
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    fonts: set[str] = set()
    for layer in doc.get("layers", []):
        t = layer.get("type")
        if not layer.get("visible", True) or t == "group":
            continue
        name = quoteattr(str(layer.get("name") or t)[:80])
        op = float(layer.get("opacity", 1))
        g = f'<g id={name} transform="{_transform(layer)}"' + (f' opacity="{op:g}"' if op < 1 else "") + ">"
        w, h = float(layer.get("width", 1)), float(layer.get("height", 1))
        if t == "rect":
            r = float(layer.get("cornerRadius") or 0)
            out.append(f'{g}<rect width="{w:g}" height="{h:g}" rx="{r:g}" fill={quoteattr(_color(layer.get("fill")))}{_stroke(layer)}/></g>')
        elif t == "ellipse":
            out.append(f'{g}<ellipse cx="{w / 2:g}" cy="{h / 2:g}" rx="{w / 2:g}" ry="{h / 2:g}" '
                       f'fill={quoteattr(_color(layer.get("fill")))}{_stroke(layer)}/></g>')
        elif t == "line":
            pts = layer.get("points") or []
            if len(pts) >= 4:
                p = " ".join(f"{pts[i]:g},{pts[i + 1]:g}" for i in range(0, len(pts) - 1, 2))
                out.append(f'{g}<polyline points="{p}" fill="none" stroke={quoteattr(layer.get("stroke") or "#000000")} '
                           f'stroke-width="{float(layer.get("strokeWidth", 2)):g}" stroke-linecap="round"/></g>')
        elif t == "text":
            size = float(layer.get("fontSize", 32))
            family = str(layer.get("fontFamily") or "Inter")
            fonts.add(family)
            style = str(layer.get("fontStyle") or "normal")
            font = get_font(family, int(size), style)
            spacing = float(layer.get("letterSpacing") or 0)
            lh = size * float(layer.get("lineHeight") or 1.2)
            lines = _wrap(measure, str(layer.get("text", "")), font, w, spacing)
            align = layer.get("align", "left")
            anchor, ax = {"center": ("middle", w / 2), "right": ("end", w)}.get(align, ("start", 0))
            weight = "bold" if "bold" in style else "normal"
            italic = "italic" if "italic" in style else "normal"
            spans = "".join(f'<tspan x="{ax:g}" y="{(i * lh) + (lh - size) / 2 + size * 0.8:.2f}">{escape(line)}</tspan>'
                            for i, line in enumerate(lines))
            ls = f' letter-spacing="{spacing:g}"' if spacing else ""
            out.append(f'{g}<text font-family={quoteattr(family)} font-size="{size:g}" font-weight="{weight}" font-style="{italic}" '
                       f'fill={quoteattr(layer.get("fill") or "#000000")} text-anchor="{anchor}"{ls}>{spans}</text></g>')
        elif t == "image":
            tile = _layer_image({**layer, "opacity": 1})
            if tile is None:
                continue
            buf = io.BytesIO()
            tile.save(buf, "PNG", optimize=True)
            b64 = base64.b64encode(buf.getvalue()).decode()
            out.append(f'{g}<image width="{tile.width}" height="{tile.height}" preserveAspectRatio="none" '
                       f'href="data:image/png;base64,{b64}" xlink:href="data:image/png;base64,{b64}"/></g>')
    out.append("</svg>")
    if fonts:  # help design tools find the fonts (Google Fonts)
        fam = "&amp;".join("family=" + f.replace(" ", "+") for f in sorted(fonts))
        out.insert(1, f'<defs><style>@import url("https://fonts.googleapis.com/css2?{fam}&amp;display=swap");</style></defs>')
    return "\n".join(out)
