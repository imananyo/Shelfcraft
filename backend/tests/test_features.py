"""End-to-end feature flows through the API with jobs run inline.

Image AI is not configured in tests, so composites use the labeled non-AI gradient backdrop;
background removal (rembg) is real. Text AI is stubbed with a deterministic fake LLM.
"""
from __future__ import annotations

import io
import json
import zipfile

import pytest
from PIL import Image

from app.ai import fallback_manager as fm
from app.ai.base import TextResult
from tests.conftest import make_png, run_pending_jobs

LISTING_JSON = {
    "title": "Trailhead Steel Bottle 750 ml – Double-Wall Insulated",
    "bullets": ["KEEPS COLD: 24 hours cold.", "LEAKPROOF: Twist cap.", "LIGHT: 340 g.", "EASY CLEAN: Wide mouth.",
                "BUILT TO LAST: 18/8 steel."],
    "description": "A bottle for every trail.", "keywords": ["water bottle", "insulated"],
    "search_terms": "hiking flask thermos", "benefits": ["Cold drinks all day"], "feature_explanations": [],
    "image_strategy": [{"slot": "infographic_features", "concept": "callouts", "headline": "Built for the trail",
                        "callouts": ["24h cold", "Leakproof", "340 g", "Wide mouth"]}],
    "listing_structure": [], "creative_recommendations": [], "headline": "Built for the trail",
    "subheadline": "Insulated steel", "assumptions": ["Capacity assumed from name"],
}


@pytest.fixture
def fake_llm(monkeypatch):
    def fake(req, *, purpose, preferred=None, strict=False):
        if purpose == "product_research":
            data = {"summary": "s", "personas": [{"name": "Hiker"}], "usps": ["light"], "assumptions": ["a"],
                    "review_sentiment": {"overall": "no data"}}
        elif purpose.startswith("listing_title"):
            data = {"title": "Rewritten title"}
        else:
            data = LISTING_JSON
        return TextResult(text=json.dumps(data), provider="fake", model="fake-1")

    monkeypatch.setattr(fm, "generate_text", fake)
    import app.services.copywriting as cw

    monkeypatch.setattr(cw.fm, "generate_text", fake)


@pytest.fixture(scope="module")
def product(client):
    b = client.post("/api/brands", json={"name": "Trailhead", "colors": ["#14532d", "#f59e0b"]}).json()
    p = client.post("/api/products", json={"name": "Trail Bottle", "brand_id": b["id"], "category": "Outdoor",
                                           "features": ["Double-wall steel", "Leakproof cap", "Wide mouth"],
                                           "benefits": ["Cold for 24h", "No spills", "Easy to clean"],
                                           "specifications": {"Width": "7 cm", "Height": "25 cm"},
                                           "variants": [{"name": "Forest", "attributes": {"hex": "#166534"}}]}).json()
    client.post(f"/api/products/{p['id']}/images", files=[("files", ("p.png", make_png(600, 600), "image/png"))])
    return client.get(f"/api/products/{p['id']}").json()


def test_research_and_listing_flow(client, product, fake_llm):
    r = client.post(f"/api/products/{product['id']}/research", json={"reviews": "Love it. Leaks sometimes."})
    assert r.status_code == 202
    assert run_pending_jobs() == ["succeeded"]
    res = client.get(f"/api/products/{product['id']}/research").json()
    assert res[0]["provider"] == "fake" and res[0]["inputs"]["reviews_chars"] > 0

    lst = client.post("/api/listings", json={"product_id": product["id"], "marketplace": "amazon"}).json()
    assert run_pending_jobs() == ["succeeded"]
    full = client.get(f"/api/listings/{lst['id']}").json()
    assert full["copy"]["title"].startswith("Trailhead") and len(full["copy"]["bullets"]) == 5
    assert full["provenance"]["provider"] == "fake"
    # Edit, save version, regenerate a single field, restore.
    edited = {**full["copy"], "title": "x" * 210}
    saved = client.put(f"/api/listings/{lst['id']}/copy", json={"copy": edited, "save_version": True}).json()
    assert any(w["field"] == "title" for w in saved["warnings"])
    client.post(f"/api/listings/{lst['id']}/generate", json={"field": "title"})
    run_pending_jobs()
    assert client.get(f"/api/listings/{lst['id']}").json()["copy"]["title"] == "Rewritten title"
    assert client.post(f"/api/listings/{lst['id']}/restore/0").status_code == 200
    for fmt in ("txt", "json", "csv"):
        e = client.get(f"/api/listings/{lst['id']}/export", params={"format": fmt})
        assert e.status_code == 200 and len(e.content) > 20


def test_listing_image_set_uses_copy_strategy(client, product, fake_llm):
    lst = client.post("/api/listings", json={"product_id": product["id"], "marketplace": "amazon"}).json()
    run_pending_jobs()
    r = client.post(f"/api/listings/{lst['id']}/images", json={"slots": ["main_white", "infographic_features", "comparison"]})
    assert r.status_code == 202
    assert run_pending_jobs() == ["succeeded"]
    full = client.get(f"/api/listings/{lst['id']}").json()
    assert [i["slot"] for i in full["images"]] == ["main_white", "infographic_features", "comparison"]
    assert not full["image_errors"]
    # The feature-callout image used the copy's image strategy callouts as editable text.
    doc_id = next(i["document_id"] for i in full["images"] if i["slot"] == "infographic_features")
    texts = [l["text"] for l in client.get(f"/api/documents/{doc_id}").json()["document"]["layers"] if l["type"] == "text"]
    assert "Built for the trail" in texts and "24h cold" in texts


def test_white_background_main_image_uses_real_cutout(client, product):
    r = client.post("/api/creative/generate", json={"creative_type": "white_bg_main", "product_id": product["id"],
                                                    "width": 1000, "height": 1000})
    assert r.status_code == 202
    assert run_pending_jobs() == ["succeeded"]
    s = client.get(f"/api/creative/sessions/{r.json()['session_id']}").json()
    a = s["assets"][0]
    assert a["provider"] == "rembg" and a["width"] == 1000
    im = Image.open(io.BytesIO(client.get(a["url"]).content)).convert("RGB")
    assert im.getpixel((5, 5)) == (255, 255, 255)  # pure white corners
    assert im.getpixel((500, 500)) != (255, 255, 255)  # product present


def test_composite_without_image_ai_is_labeled_non_ai(client, product):
    r = client.post("/api/creative/generate", json={"creative_type": "hero", "product_id": product["id"],
                                                    "width": 768, "height": 768})
    assert run_pending_jobs() == ["succeeded"]
    a = client.get(f"/api/creative/sessions/{r.json()['session_id']}").json()["assets"][0]
    assert a["is_ai_generated"] is False and "non-AI" in a["model"]
    assert a["meta"]["document_id"]  # layered, editable version saved


def test_ai_background_path_is_attributed_and_does_not_lock_db(client, product, monkeypatch):
    """Simulates a real image provider that logs usage (a DB write) mid-generation."""
    from app.ai.base import ImageResult
    from app.db.models import Notification
    from app.db.session import session_scope
    import app.services.creative as creative

    def fake_image(req, *, purpose, preferred=None, strict=False):
        with session_scope() as db:  # would raise "database is locked" if the job held the write lock
            db.add(Notification(title="usage-log-probe"))
        return ImageResult(image_png=make_png(512, 512, "#a8dadc", with_object=False), provider="fakeimg",
                           model="fake-diffusion")

    monkeypatch.setattr(creative.fm, "generate_image", fake_image)
    r = client.post("/api/creative/generate", json={"creative_type": "lifestyle", "product_id": product["id"],
                                                    "width": 768, "height": 768})
    assert run_pending_jobs() == ["succeeded"]
    a = client.get(f"/api/creative/sessions/{r.json()['session_id']}").json()["assets"][0]
    assert a["is_ai_generated"] is True and a["provider"] == "fakeimg" and a["model"] == "fake-diffusion"
    assert "product pixels are from your photo" in a["meta"]["note"]


def test_template_infographic_renders_text_layers(client, product):
    r = client.post("/api/creative/generate", json={"creative_type": "feature", "product_id": product["id"]})
    assert run_pending_jobs() == ["succeeded"]
    a = client.get(f"/api/creative/sessions/{r.json()['session_id']}").json()["assets"][0]
    doc = client.get(f"/api/documents/{a['meta']['document_id']}").json()["document"]
    texts = [layer["text"] for layer in doc["layers"] if layer["type"] == "text" and layer["visible"]]
    assert "Cold for 24h" in texts and all("{{" not in t for t in texts)


def test_editor_document_persist_version_conflict_revisions_export(client):
    d = client.post("/api/documents", json={"name": "Poster", "width": 800, "height": 600}).json()
    doc = d["document"]
    doc["layers"] = [{"id": "t1", "type": "text", "name": "Title", "x": 40, "y": 40, "width": 600, "height": 80,
                      "rotation": 0, "opacity": 1, "locked": False, "visible": True, "text": "Hello", "fontSize": 48,
                      "fill": "#111111", "fontFamily": "Inter"},
                     {"id": "r1", "type": "rect", "name": "Box", "x": 100, "y": 200, "width": 200, "height": 100,
                      "rotation": 15, "opacity": 0.8, "locked": True, "visible": True, "fill": "#0f766e", "cornerRadius": 12}]
    s = client.put(f"/api/documents/{d['id']}", json={"document": doc, "base_version": d["version"], "checkpoint": True,
                                                       "thumbnail": True})
    assert s.status_code == 200 and s.json()["version"] == d["version"] + 1 and s.json()["thumb_url"]
    stale = client.put(f"/api/documents/{d['id']}", json={"document": doc, "base_version": d["version"]})
    assert stale.status_code == 409
    got = client.get(f"/api/documents/{d['id']}").json()["document"]
    assert [layer["id"] for layer in got["layers"]] == ["t1", "r1"] and got["layers"][1]["locked"] is True
    assert len(client.get(f"/api/documents/{d['id']}/revisions").json()) == 1
    png = client.get(f"/api/documents/{d['id']}/export", params={"format": "png"})
    assert png.status_code == 200 and Image.open(io.BytesIO(png.content)).size == (800, 600)
    jpg = client.get(f"/api/documents/{d['id']}/export", params={"format": "jpeg", "scale": 0.5})
    assert Image.open(io.BytesIO(jpg.content)).size == (400, 300)
    js = client.get(f"/api/documents/{d['id']}/export", params={"format": "json"}).json()
    imp = client.post("/api/documents/import", json=js)
    assert imp.status_code == 201
    bad = client.put(f"/api/documents/{d['id']}", json={"document": {**doc, "width": 99999}})
    assert bad.status_code == 422


def test_aplus_create_reorder_export(client, product):
    a = client.post("/api/aplus", json={"name": "Bottle A+", "product_id": product["id"], "tier": "premium",
                                        "modules": ["hero_banner", "feature_row", "comparison"]}).json()
    assert len(a["modules"]) == 3
    ids = [m["document_id"] for m in a["modules"]]
    r = client.put(f"/api/aplus/{a['id']}/order", json={"document_ids": list(reversed(ids))}).json()
    assert [m["document_id"] for m in r["modules"]] == list(reversed(ids))
    r = client.post(f"/api/aplus/{a['id']}/modules", json={"type": "brand_story"}).json()
    assert len(r["modules"]) == 4
    assert client.get(f"/api/aplus/{a['id']}/preview.png").status_code == 200
    z = client.post(f"/api/aplus/{a['id']}/export.zip")
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert "modules.json" in names and sum(n.endswith(".jpg") for n in names) == 4
    assert any("1464x600" in n for n in names)


def test_factory_bounded_queue_retry_cancel_zip(client, product):
    body = {"name": "Run", "product_ids": [product["id"]], "creative_types": ["white_bg_main", "feature"],
            "include_variants": True}
    prev = client.post("/api/factory/preview", json=body).json()
    assert prev["count"] == 2 and prev["estimated_minutes"] > 0
    too_many = client.post("/api/factory/preview", json={**body, "creative_types": ["feature"] * 10,
                                                         "product_ids": [product["id"]] * 30}).json()
    assert too_many["count"] == 300 and too_many["warnings"]
    over = client.post("/api/factory/batches", json={**body, "creative_types": ["feature"] * 10,
                                                     "product_ids": [product["id"]] * 30})
    assert over.status_code == 422
    b = client.post("/api/factory/batches", json=body).json()
    assert b["total"] == 2
    assert set(run_pending_jobs()) == {"succeeded"}
    done = client.get(f"/api/factory/batches/{b['id']}").json()
    assert done["counts"] == {"succeeded": 2} and done["progress"] == 1.0
    z = client.get(f"/api/factory/batches/{b['id']}/download")
    assert z.status_code == 200 and len(zipfile.ZipFile(io.BytesIO(z.content)).namelist()) >= 2
    assert client.post(f"/api/factory/batches/{b['id']}/cancel").json()["cancelled"] == 0


def test_video_composition_exports_valid_mp4(client, product):
    from app.services.video import find_tool

    if not find_tool("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    v = client.post("/api/videos", json={"name": "Bottle reel", "product_id": product["id"], "aspect": "9:16",
                                         "target_duration": 6}).json()
    assert v["scenes"]
    extra = client.post("/api/assets", files={"files": ("s2.png", make_png(500, 500, "#264653"), "image/png")}).json()[0]
    scenes = v["scenes"][:1] + [{"asset_id": extra["id"], "duration": 2, "text": "Leakproof", "motion": "zoom_out"}]
    client.patch(f"/api/videos/{v['id']}", json={"scenes": scenes, "transition": "slideleft", "transition_s": 0.5})
    assert client.post(f"/api/videos/{v['id']}/render").status_code == 202
    assert run_pending_jobs() == ["succeeded"]
    out = client.get(f"/api/videos/{v['id']}").json()
    assert out["last_render"]["duration_s"] > 2
    data = client.get(out["last_render"]["url"]).content
    assert data[4:8] == b"ftyp"
    from app.services.video import probe_duration
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "v.mp4"
        p.write_bytes(data)
        dur = probe_duration(p)
    assert dur is None or abs(dur - out["last_render"]["duration_s"]) < 0.6


def test_spot_edits_label_ai_vs_non_ai(client):
    a = client.post("/api/assets", files={"files": ("e.png", make_png(300, 300), "image/png")}).json()[0]
    for op, extra in (("enhance", {}), ("upscale", {}), ("recolor", {"color": "#ff0000"})):
        r = client.post("/api/edits", json={"asset_id": a["id"], "operation": op, **extra})
        assert r.status_code == 202
        run_pending_jobs()
        res = client.get(f"/api/jobs/{r.json()['id']}").json()
        assert res["status"] == "succeeded", res
        assert res["result"]["ai"] is False and "non-AI" in res["result"]["model"]
    # Object removal with the classical engine needs a mask.
    no_mask = client.post("/api/edits", json={"asset_id": a["id"], "operation": "remove_object", "engine": "opencv"})
    run_pending_jobs()
    assert client.get(f"/api/jobs/{no_mask.json()['id']}").json()["status"] == "failed"
    m = Image.new("L", (300, 300), 0)
    m.paste(255, (120, 100, 180, 160))
    buf = io.BytesIO()
    m.save(buf, "PNG")
    import base64

    data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    r = client.post("/api/edits", json={"asset_id": a["id"], "operation": "remove_object", "engine": "opencv",
                                        "mask": data_url})
    run_pending_jobs()
    res = client.get(f"/api/jobs/{r.json()['id']}").json()
    assert res["status"] == "succeeded" and res["result"]["provider"] == "opencv"
    bg = client.post("/api/edits", json={"asset_id": a["id"], "operation": "replace_background",
                                         "background_mode": "color", "color": "#000000"})
    run_pending_jobs()
    assert client.get(f"/api/jobs/{bg.json()['id']}").json()["result"]["provider"] == "rembg"


def test_inspire_analysis_and_generation(client, product):
    ref = client.post("/api/assets", files={"files": ("ref.png", make_png(800, 800, "#e63946"), "image/png")}).json()[0]
    an = client.post("/api/inspire/analyze", json={"asset_id": ref["id"], "use_vision": False}).json()
    assert len(an["palette"]) >= 2 and an["layout"]["grid"] in ("split", "centered", "rule-of-thirds")
    r = client.post("/api/inspire/generate", json={"reference_asset_id": ref["id"], "product_id": product["id"]})
    assert r.status_code == 202
    assert run_pending_jobs() == ["succeeded"]
    res = client.get(f"/api/jobs/{r.json()['id']}").json()["result"]
    assert res["document_id"] and res["asset_ids"]


def test_restart_persistence(client):
    """Projects survive an engine re-init (simulated restart)."""
    from app.config import get_settings
    from app.db.session import init_engine

    p = client.post("/api/projects", json={"name": "Persist me", "width": 500, "height": 500}).json()
    init_engine(get_settings().sqlalchemy_url)
    assert client.get(f"/api/projects/{p['id']}").json()["name"] == "Persist me"
