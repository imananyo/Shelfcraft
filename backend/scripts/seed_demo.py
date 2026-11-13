"""Optional: create a small demo brand + products so you can explore Shelfcraft immediately.

Usage (backend running):  .venv\\Scripts\\python.exe scripts\\seed_demo.py [--api http://127.0.0.1:8000]
The product photo is generated locally from simple shapes (or uses data/bench images if present);
it is clearly named as demo content. Delete the demo brand/products any time from the UI.
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[2]


def mug_photo() -> bytes:
    bench = ROOT / "data" / "bench" / "bench_0.png"
    if bench.exists():
        return bench.read_bytes()
    im = Image.new("RGB", (900, 900), "#efe9e1")
    d = ImageDraw.Draw(im)
    d.ellipse((230, 700, 670, 760), fill="#d9d1c6")
    d.rounded_rectangle((280, 260, 620, 730), radius=40, fill="#2f6f67")
    d.ellipse((560, 380, 720, 600), outline="#2f6f67", width=38)
    im = im.filter(ImageFilter.SMOOTH)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def bottle_photo() -> bytes:
    im = Image.new("RGB", (900, 900), "#f3f1ee")
    d = ImageDraw.Draw(im)
    d.ellipse((330, 790, 570, 830), fill="#dcd6cd")
    d.rounded_rectangle((350, 250, 550, 810), radius=60, fill="#1f2937")
    d.rounded_rectangle((385, 170, 515, 260), radius=20, fill="#9ca3af")
    d.rectangle((350, 420, 550, 560), fill="#f59e0b")
    buf = io.BytesIO()
    im.filter(ImageFilter.SMOOTH).save(buf, "PNG")
    return buf.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--token", default=None)
    a = ap.parse_args()
    headers = {"X-Shelfcraft-Token": a.token} if a.token else {}
    c = httpx.Client(base_url=f"{a.api}/api", headers=headers, timeout=60)
    brand = c.post("/brands", json={
        "name": "Hearth & Field (demo)", "colors": ["#2f6f67", "#e9a23b", "#f6f1ea", "#1f2a28"], "primary_font": "Fraunces",
        "secondary_font": "Manrope", "tagline": "Everyday pieces, made to last", "tone_of_voice": "Warm, honest, quietly confident",
        "target_audience": "Home cooks and coffee lovers who value craft and durability over trends.",
        "values": ["Craft", "Durability", "Honesty"], "aesthetic": ["Natural", "Earthy", "Minimal"],
        "visual_identity": "Soft natural light, linen and wood, muted earthy tones, generous negative space.",
        "marketing_guidelines": "Never claim dishwasher-proof glaze lasts forever. No medical or eco claims without proof.",
    }).raise_for_status().json()
    mug = c.post("/products", json={
        "name": "Stoneware Coffee Mug 12 oz (demo)", "brand_id": brand["id"], "category": "Kitchen & Dining", "sku": "HF-MUG-12",
        "price": 24.0, "description": "Hand-glazed stoneware mug with a speckled finish and a comfortable wide handle.",
        "features": ["Hand-glazed stoneware", "12 oz / 355 ml capacity", "Wide comfortable handle", "Microwave safe"],
        "benefits": ["Keeps coffee warm longer", "Unique speckled finish", "Comfortable grip", "Easy everyday use"],
        "specifications": {"Width": "9 cm", "Height": "10 cm", "Capacity": "355 ml", "Material": "Stoneware"},
        "variants": [{"name": "Sage", "attributes": {"hex": "#8aa39b"}}, {"name": "Clay", "attributes": {"hex": "#c4704f"}}],
    }).raise_for_status().json()
    c.post(f"/products/{mug['id']}/images", files=[("files", ("mug-demo.png", mug_photo(), "image/png"))]).raise_for_status()
    bottle = c.post("/products", json={
        "name": "Insulated Trail Bottle 750 ml (demo)", "brand_id": brand["id"], "category": "Outdoor", "sku": "HF-BTL-750", "price": 32.0,
        "description": "Double-wall vacuum insulated steel bottle with a leakproof cap.",
        "features": ["Double-wall vacuum insulation", "Leakproof screw cap", "18/8 stainless steel", "Powder-coat finish"],
        "benefits": ["Cold for up to 24 hours", "No spills in your bag", "No metallic taste", "Grippy, scratch-resistant"],
        "specifications": {"Width": "7.5 cm", "Height": "26 cm", "Capacity": "750 ml"},
    }).raise_for_status().json()
    c.post(f"/products/{bottle['id']}/images", files=[("files", ("bottle-demo.png", bottle_photo(), "image/png"))]).raise_for_status()
    doc = c.post("/documents", json={"name": "Demo poster", "width": 1080, "height": 1350, "document": {
        "width": 1080, "height": 1350, "background": "#f6f1ea", "layers": [
            {"id": "bg1", "type": "rect", "name": "Band", "x": 0, "y": 980, "width": 1080, "height": 370, "rotation": 0, "opacity": 1,
             "locked": False, "visible": True, "fill": "#2f6f67", "cornerRadius": 0},
            {"id": "t1", "type": "text", "name": "Headline", "x": 80, "y": 90, "width": 920, "height": 200, "rotation": 0, "opacity": 1,
             "locked": False, "visible": True, "text": "Slow mornings, made better", "fontFamily": "Fraunces", "fontSize": 92,
             "fontStyle": "bold", "fill": "#1f2a28", "align": "left", "lineHeight": 1.05},
            {"id": "t2", "type": "text", "name": "CTA", "x": 80, "y": 1110, "width": 920, "height": 80, "rotation": 0, "opacity": 1,
             "locked": False, "visible": True, "text": "Hand-glazed stoneware · 12 oz", "fontFamily": "Manrope", "fontSize": 44,
             "fill": "#f6f1ea", "align": "left", "lineHeight": 1.2},
        ]}}).raise_for_status().json()
    print(f"Demo data created: brand {brand['id']}, products {mug['id']}, {bottle['id']}, design {doc['id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
