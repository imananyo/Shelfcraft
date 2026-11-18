"""Tests for grader, translate, packaging, ads, playbooks, apply-to-product, image→layers, spin, voiceover,
bulk copy, seamless A+, Amazon Mobile, paste import, Amazon connector, public API, MCP server and team mode."""
from __future__ import annotations

import io
import json
import zipfile

import pytest
from PIL import Image, ImageDraw

from app.ai import fallback_manager as fm
from app.ai.base import TextResult
from tests.conftest import make_png, run_pending_jobs


def fake_text(req, *, purpose, preferred=None, strict=False):
    if purpose == "translate":
        n = req.prompt.count("\n") - req.prompt.split("\n\n", 1)[0].count("\n")
        items = [line.split(". ", 1)[1] for line in req.prompt.split("\n\n", 1)[1].split("\n")]
        data = {"items": [f"DE: {t}" if t else t for t in items]}
        assert len(items) >= 1, n
    elif purpose == "packaging_ideas":
        data = {"concepts": [{"name": f"Concept {i}", "big_idea": "Kraft sleeve", "structure": "sleeve", "materials": "kraft",
                              "palette": ["#2f6f67", "#e9a23b", "#f6f1ea"], "front_panel_copy": "Made to last"} for i in range(15)],
                "assumptions": ["Retail shelf"]}
    elif purpose == "ad_concepts":
        data = {"concepts": [{"persona": "Hiker", "angle": f"angle {i}", "headline": f"Headline {i}", "subheadline": "Sub", "cta": "Shop",
                              "visual": "trail at dawn", "hypothesis": "h"} for i in range(6)]}
    elif purpose == "voiceover_script":
        data = {"lines": ["Meet your new favourite bottle.", "It keeps drinks cold all day."]}
    elif purpose == "listing_grader":
        data = {"strengths": ["clear"], "weaknesses": ["vague"], "rewrite_suggestions": [], "unanswered_questions": ["Dishwasher safe?"]}
    else:
        data = {"title": "Trailhead Steel Bottle 750 ml", "bullets": ["KEEPS COLD: 24 hours.", "LEAKPROOF: Twist cap."], "description": "d",
                "keywords": ["bottle"], "search_terms": "flask", "image_strategy": [], "headline": "Built for the trail", "subheadline": "s"}
    return TextResult(text=json.dumps(data), provider="fake", model="fake-1")


@pytest.fixture
def llm(monkeypatch):
    monkeypatch.setattr(fm, "generate_text", fake_text)
    import app.services.copywriting as cw
    import app.services.growth as gr

    monkeypatch.setattr(cw.fm, "generate_text", fake_text)
    monkeypatch.setattr(gr.fm, "generate_text", fake_text)


@pytest.fixture(scope="module")
def prod(client):
    p = client.post("/api/products", json={"name": "Trail Bottle G", "category": "Outdoor", "features": ["Steel", "Leakproof", "Wide mouth"],
                                           "benefits": ["Cold 24h", "No spills", "Easy clean"], "specifications": {"Width": "7 cm", "Height": "25 cm"}}).json()
    client.post(f"/api/products/{p['id']}/images", files=[("files", ("g.png", make_png(600, 600), "image/png"))])
    return client.get(f"/api/products/{p['id']}").json()


def _png_bytes(im: Image.Image) -> bytes:
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


# ---------------------------------------------------------------- grader
def test_grader_scores_good_vs_bad(client):
    bad = client.post("/api/grader", json={"title": "BEST SALE!!! bottle", "bullets": ["good"], "search_terms": "", "description": ""}).json()
    good = client.post("/api/grader", json={
        "title": "Trailhead Insulated Steel Water Bottle 750 ml – Leakproof, Keeps Drinks Cold 24 Hours", "brand": "Trailhead",
        "bullets": [f"BENEFIT {i}: A clear, specific sentence explaining a real benefit of this bottle in daily use." for i in range(5)],
        "description": "A durable bottle.\n\n" + "Details about materials and care. " * 15, "search_terms": "flask thermos hiking gym",
        "keywords": ["water bottle"]}).json()
    assert good["score"] > bad["score"] + 25 and bad["grade"] in ("D", "F")
    assert any(f["section"] == "title" for f in bad["top_fixes"])
    assert {s["key"] for s in good["sections"]} == {"title", "bullets", "description", "search_terms", "images", "aplus"}


def test_grader_detects_white_main_image(client):
    white = Image.new("RGB", (1200, 1200), "white")
    ImageDraw.Draw(white).rectangle((200, 120, 1000, 1080), fill="#2a9d8f")
    a = client.post("/api/assets", files={"files": ("w.png", _png_bytes(white), "image/png")}).json()[0]
    grey = client.post("/api/assets", files={"files": ("g.png", make_png(500, 500), "image/png")}).json()[0]
    r1 = client.post("/api/grader", json={"title": "x", "asset_ids": [a["id"]]}).json()
    r2 = client.post("/api/grader", json={"title": "x", "asset_ids": [grey["id"]]}).json()
    chk = lambda r: next(c for s in r["sections"] if s["key"] == "images" for c in s["checks"] if c["label"].startswith("Main image"))  # noqa: E731
    assert chk(r1)["passed"] is True and chk(r2)["passed"] is False


def test_grader_ai_review(client, llm):
    r = client.post("/api/grader", json={"title": "Bottle", "ai_review": True}).json()
    assert r["ai_review"]["provider"] == "fake" and r["ai_review"]["unanswered_questions"]


# ---------------------------------------------------------------- listings: translate, bulk, mobile
def test_translate_listing_copy_and_image_text(client, prod, llm):
    lst = client.post("/api/listings", json={"product_id": prod["id"], "marketplace": "amazon_mobile"}).json()
    run_pending_jobs()
    client.post(f"/api/listings/{lst['id']}/images", json={"slots": ["infographic_features"]})
    run_pending_jobs()
    j = client.post(f"/api/listings/{lst['id']}/translate", json={"language": "de", "country": "DE"}).json()
    assert run_pending_jobs() == ["succeeded"]
    new_id = client.get(f"/api/jobs/{j['id']}").json()["result"]["project_id"]
    t = client.get(f"/api/listings/{new_id}").json()
    assert t["copy"]["title"].startswith("DE: ") and t["options"]["language"] == "de"
    doc_id = t["images"][0]["document_id"]
    texts = [layer["text"] for layer in client.get(f"/api/documents/{doc_id}").json()["document"]["layers"] if layer["type"] == "text" and layer["text"]]
    assert texts and all(x.startswith("DE: ") for x in texts)
    assert t["limits"]["title"]["max_chars"] == 80  # Amazon Mobile guidance


def test_bulk_listing_copy(client, prod, llm):
    p2 = client.post("/api/products", json={"name": "Second Bottle"}).json()
    r = client.post("/api/listings/bulk", json={"product_ids": [prod["id"], p2["id"]]}).json()
    assert r["total"] == 2
    assert run_pending_jobs() == ["succeeded", "succeeded"]
    runs = client.get("/api/scale/runs").json()
    assert any(x["id"] == r["batch_id"] and x["kind"] == "bulk_copy" for x in runs)


def test_factory_listing_copy_type(client, prod, llm):
    b = client.post("/api/factory/batches", json={"name": "copy", "product_ids": [prod["id"]], "creative_types": ["listing_copy"]}).json()
    assert run_pending_jobs() == ["succeeded"]
    assert client.get(f"/api/factory/batches/{b['id']}").json()["counts"] == {"succeeded": 1}


# ---------------------------------------------------------------- packaging & ads
def test_packaging_ideas_15(client, prod, llm):
    j = client.post("/api/labs/packaging", json={"product_id": prod["id"], "count": 15}).json()
    assert run_pending_jobs() == ["succeeded"]
    pid = client.get(f"/api/jobs/{j['id']}").json()["result"]["project_id"]
    data = client.get(f"/api/labs/packaging/{pid}").json()
    assert len(data["concepts"]) == 15 and data["provider"] == "fake"


def test_ads_concepts_and_render(client, prod, llm):
    a = client.post("/api/ads", json={"product_id": prod["id"], "format": "sb_image", "count": 6}).json()
    assert run_pending_jobs() == ["succeeded"]
    ad = client.get(f"/api/ads/{a['id']}").json()
    assert len(ad["concepts"]) == 6
    client.post(f"/api/ads/{a['id']}/render", json={"indices": [0, 1]})
    assert run_pending_jobs() == ["succeeded", "succeeded"]
    ad = client.get(f"/api/ads/{a['id']}").json()
    assert set(ad["renders"]) == {"0", "1"}
    doc = client.get(f"/api/documents/{ad['renders']['0']['document_id']}").json()["document"]
    assert doc["width"] == 1200 and doc["height"] == 628
    assert "Headline 0" in [layer.get("text") for layer in doc["layers"]]


# ---------------------------------------------------------------- playbooks & apply to product
def test_playbook_library_import_edit_run(client, prod):
    lib = client.get("/api/playbooks", params={"templates": True}).json()
    assert {"Marketplace main image set", "Full launch kit"} <= {p["name"] for p in lib}
    t = next(p for p in lib if p["name"] == "Lifestyle trio")
    mine = client.post(f"/api/playbooks/{t['id']}/import").json()
    assert mine["is_template"] is False
    upd = client.put(f"/api/playbooks/{mine['id']}", json={"name": "My kit", "steps": [{"kind": "creative", "creative_type": "white_bg_main"},
                                                                                         {"kind": "creative", "creative_type": "feature"}]}).json()
    assert len(upd["steps"]) == 2
    bad = client.put(f"/api/playbooks/{mine['id']}", json={"name": "x", "steps": [{"kind": "nope"}]})
    assert bad.status_code == 422
    run = client.post(f"/api/playbooks/{mine['id']}/run", json={"product_ids": [prod["id"]]}).json()
    assert run["total"] == 2
    assert run_pending_jobs() == ["succeeded", "succeeded"]


def test_playbook_steps_are_cleaned_and_checked(client, prod):
    mine = client.post("/api/playbooks", json={"name": "  Kit  ", "settings": {"style": "luxury", "junk": 1}, "steps": [
        # stale keys from a previous step kind must be dropped
        {"kind": "listing_copy", "marketplace": "walmart", "language": "de", "creative_type": "hero", "extra_prompt": "x"},
        {"kind": "video", "aspect": "9:16", "duration": "20", "voiceover": 1, "tier": "basic"},
        {"kind": "aplus", "tier": "mobile", "modules": ["hero_banner", "brand_story"]},
        {"kind": "packaging", "count": 5}]}).json()
    assert mine["name"] == "Kit" and mine["settings"] == {"style": "luxury"}
    assert mine["steps"][0] == {"kind": "listing_copy", "marketplace": "walmart", "language": "de"}
    assert mine["steps"][1] == {"kind": "video", "aspect": "9:16", "duration": 20, "voiceover": True}
    assert mine["estimate_minutes"] > 0
    for bad in ([{"kind": "creative"}], [{"kind": "creative", "creative_type": "hero", "style": "neon"}],
                [{"kind": "video", "duration": 999}], [{"kind": "listing_copy", "marketplace": "ebay"}],
                [{"kind": "aplus", "modules": ["nope"]}], [{"kind": "creative", "creative_type": "hero", "width": 10}]):
        r = client.put(f"/api/playbooks/{mine['id']}", json={"name": "x", "steps": bad})
        assert r.status_code == 422, bad
    opts = client.get("/api/playbooks/options").json()
    assert "white_bg_main" in opts["creative_types"] and "de" in opts["languages"] and "hero_banner" in opts["aplus_modules"]


def test_playbook_duplicate_runs_history_and_dedupe(client, prod):
    mine = client.post("/api/playbooks", json={"name": "Solo", "steps": [{"kind": "creative", "creative_type": "white_bg_main"}]}).json()
    dup = client.post(f"/api/playbooks/{mine['id']}/import").json()
    assert dup["name"] == "Solo (copy)" and dup["id"] != mine["id"]
    assert client.post(f"/api/playbooks/{mine['id']}/run", json={"product_ids": ["missing"]}).status_code == 404
    run = client.post(f"/api/playbooks/{mine['id']}/run", json={"product_ids": [prod["id"], prod["id"]]}).json()
    assert run["total"] == 1 and run["estimate_minutes"] > 0
    run_pending_jobs()
    runs = client.get(f"/api/playbooks/{mine['id']}/runs").json()
    assert [r["id"] for r in runs] == [run["batch_id"]] and runs[0]["counts"] == {"succeeded": 1}
    assert client.get(f"/api/playbooks/{dup['id']}/runs").json() == []
    lib = {p["name"] for p in client.get("/api/playbooks", params={"templates": True}).json()}
    assert {"Multi-marketplace copy", "EU expansion copy", "A+ & brand story"} <= lib


def test_apply_design_to_different_product(client, prod):
    other = client.post("/api/products", json={"name": "Camp Mug", "features": ["Enamel", "Stackable", "Light"],
                                                "benefits": ["Tough", "Packs small", "Lightweight"]}).json()
    client.post(f"/api/products/{other['id']}/images", files=[("files", ("m.png", make_png(500, 500, "#e76f51"), "image/png"))])
    s = client.post("/api/creative/generate", json={"creative_type": "feature", "product_id": prod["id"]}).json()
    run_pending_jobs()
    src_doc = client.get(f"/api/creative/sessions/{s['session_id']}").json()["assets"][0]["meta"]["document_id"]
    r = client.post("/api/scale/apply", json={"document_ids": [src_doc], "product_ids": [other["id"]]}).json()
    doc = client.get(f"/api/documents/{r['results'][0]['document_id']}").json()["document"]
    texts = [layer.get("text") for layer in doc["layers"] if layer["type"] == "text"]
    assert "Tough" in texts and "Cold 24h" not in texts
    imgs = [layer for layer in doc["layers"] if layer["type"] == "image"]
    assets = [client.get(f"/api/assets/{layer['assetId']}").json() for layer in imgs if layer.get("assetId")]
    assert assets and all(a["product_id"] == other["id"] for a in assets)


# ---------------------------------------------------------------- media
def test_image_to_layers_ocr(client):
    from app.imaging.fonts import get_font

    im = Image.new("RGB", (900, 700), "#f3efe6")
    d = ImageDraw.Draw(im)
    d.text((60, 50), "SUMMER SALE", font=get_font(None, 72, "bold"), fill="#1f2937")
    d.ellipse((300, 260, 620, 580), fill="#2a9d8f")
    a = client.post("/api/assets", files={"files": ("ad.png", _png_bytes(im), "image/png")}).json()[0]
    j = client.post(f"/api/assets/{a['id']}/decompose").json()
    assert run_pending_jobs() == ["succeeded"]
    res = client.get(f"/api/jobs/{j['id']}").json()["result"]
    doc = client.get(f"/api/documents/{res['document_id']}").json()["document"]
    texts = [layer["text"] for layer in doc["layers"] if layer["type"] == "text"]
    assert any("SUMMER" in t.upper() for t in texts), texts
    assert doc["layers"][0]["name"] == "Background" and doc["layers"][0]["assetId"]


def test_spin_video_from_angle_photos(client):
    from app.services.video import find_tool

    if not find_tool("ffmpeg"):
        pytest.skip("ffmpeg missing")
    ids = [client.post("/api/assets", files={"files": (f"a{i}.png", make_png(400, 400, c), "image/png")}).json()[0]["id"]
           for i, c in enumerate(["#264653", "#2a9d8f", "#e9c46a", "#f4a261"])]
    j = client.post("/api/videos/spin", json={"asset_ids": ids, "white_background": False, "loops": 1, "tween": 1}).json()
    assert run_pending_jobs() == ["succeeded"]
    r = client.get(f"/api/jobs/{j['id']}").json()["result"]
    assert r["duration_s"] > 0
    assert client.get(f"/api/assets/{r['asset_id']}/file").content[4:8] == b"ftyp"
    assert client.post("/api/videos/spin", json={"asset_ids": ids[:2]}).status_code == 422


def test_voiceover_video_offline_tts(client, prod, llm):
    from app.services.media_extra import list_voices
    from app.services.video import find_tool

    if not find_tool("ffmpeg") or not list_voices():
        pytest.skip("ffmpeg or system TTS voices unavailable")
    v = client.post("/api/videos", json={"name": "VO", "product_id": prod["id"], "aspect": "9:16", "target_duration": 4}).json()
    scenes = v["scenes"][:1] * 2
    client.patch(f"/api/videos/{v['id']}", json={"scenes": [{**s, "id": f"s{i}"} for i, s in enumerate(scenes)]})
    j = client.post(f"/api/videos/{v['id']}/voiceover", json={}).json()
    assert run_pending_jobs() == ["succeeded"]
    r = client.get(f"/api/jobs/{j['id']}").json()["result"]
    assert r["lines"] == 2 and r["duration_s"] > 1.5
    asset = client.get(f"/api/assets/{r['asset_id']}").json()
    assert "no avatar" in asset["model"]


# ---------------------------------------------------------------- A+ seamless
def test_aplus_seamless_exports_slices(client, prod):
    a = client.post("/api/aplus", json={"name": "Seam", "product_id": prod["id"], "tier": "premium", "modules": ["seamless"]}).json()
    z = zipfile.ZipFile(io.BytesIO(client.post(f"/api/aplus/{a['id']}/export.zip").content))
    jpgs = sorted(n for n in z.namelist() if n.endswith(".jpg"))
    assert len(jpgs) == 3 and all("1464x600" in n for n in jpgs)


# ---------------------------------------------------------------- import options
def test_paste_import_parses_listing():
    from app.routers.integrations import parse_listing_text

    d = parse_listing_text("Acme Bamboo Cutting Board, Large\n$24.99\n• Organic bamboo surface\n• Juice groove\n"
                           "Material: Bamboo\nThis board is made from sustainably harvested bamboo and is gentle on knives.")
    assert d["name"].startswith("Acme Bamboo") and d["price"] == 24.99 and len(d["features"]) == 2 and d["specifications"]["Material"] == "Bamboo"


def test_amazon_connector_requires_setup_and_hides_secrets(client):
    s = client.patch("/api/integrations/amazon", json={"client_id": "amzn1.app", "client_secret": "SECRET123456", "refresh_token": "Atzr|xyz"}).json()
    assert s["has_client_secret"] and "SECRET123456" not in json.dumps(s)
    r = client.post("/api/integrations/amazon/import", json={"asin": "B000000000"})
    assert r.status_code == 422 and "enable" in r.json()["detail"]


# ---------------------------------------------------------------- public API & MCP
def test_public_api_keys_scopes(client, prod):
    assert client.get("/v1/products").status_code == 401
    k = client.post("/api/api-keys", json={"name": "ro", "scopes": ["read"]}).json()
    h = {"Authorization": f"Bearer {k['key']}"}
    assert client.get("/v1/products", headers=h).status_code == 200
    assert client.post("/v1/products", headers=h, json={"name": "x"}).status_code == 403
    listed = client.get("/api/api-keys").json()
    assert all("key" not in x for x in listed) and listed[0]["request_count"] >= 1
    client.delete(f"/api/api-keys/{k['id']}")
    assert client.get("/v1/products", headers=h).status_code == 401
    assert client.get("/v1/openapi.json").status_code == 200


def test_mcp_server_tools(client, prod, monkeypatch):
    import mcp_server

    k = client.post("/api/api-keys", json={"name": "mcp"}).json()

    def _client():
        client.headers.update({"Authorization": f"Bearer {k['key']}"})
        client.base_url = client.base_url.copy_with(path="/v1/")
        return _Ctx(client)

    class _Ctx:
        def __init__(self, c): self.c = c
        def __enter__(self): return self
        def __exit__(self, *a):
            self.c.headers.pop("Authorization", None)
            self.c.base_url = self.c.base_url.copy_with(path="/")
        def request(self, method, path, **kw): return self.c.request(method, path.lstrip("/"), **kw)

    monkeypatch.setattr(mcp_server, "_client", _client)
    names = {t.name for t in __import__("asyncio").run(mcp_server.server.list_tools())}
    assert {"list_products", "create_listing", "grade_listing", "generate_creative", "wait_for_job"} <= names
    found = mcp_server.list_products("Trail Bottle G")
    assert found and found[0]["name"] == "Trail Bottle G"
    g = mcp_server.grade_listing(title="BEST SALE bottle")
    assert 0 <= g["score"] <= 100 and g["top_fixes"]


# ---------------------------------------------------------------- AI output shape (regression: keywords returned as a string)
def test_normalize_copy_coerces_model_output():
    from app.services.copywriting import normalize_copy

    c = normalize_copy({"title": ["Gold", "Ring"], "bullets": "One\nTwo", "keywords": "gold jewelry, green gemstone, ",
                        "benefits": None, "image_strategy": {"slot": "main", "callouts": "a\nb"}, "feature_explanations": "x"})
    assert c["title"] == "Gold Ring" and c["bullets"] == ["One", "Two"]
    assert c["keywords"] == ["gold jewelry", "green gemstone"] and c["benefits"] == []
    assert c["image_strategy"] == [{"slot": "main", "callouts": ["a", "b"]}] and c["feature_explanations"] == []


def test_truncated_json_is_salvaged_and_loops_deduped():
    from app.ai.base import parse_json_loose
    from app.services.copywriting import normalize_copy

    # Output cut off by the token cap while the model was looping on keywords.
    cut = '{"title": "Gold Ring", "bullets": ["A", "B"], "keywords": ["gold", "ring", "gold", "Gold", "rin'
    d = normalize_copy(parse_json_loose(cut))
    assert d["title"] == "Gold Ring" and d["bullets"] == ["A", "B"] and d["keywords"] == ["gold", "ring"]
    assert normalize_copy({"keywords": [f"k{i}" for i in range(500)]})["keywords"] == [f"k{i}" for i in range(40)]


def test_listing_copy_retries_when_first_output_is_broken(monkeypatch, client, prod):
    from app.ai import fallback_manager as fm
    from app.ai.base import TextResult
    from app.db.session import session_scope
    from app.services.copywriting import generate_listing_copy

    outputs = iter(["not json at all", '{"title": "Second try", "bullets": ["x", "y"]}'])
    calls = []

    def fake(req, **kw):
        calls.append(req.temperature)
        return TextResult(text=next(outputs), provider="ollama", model="fake", output_tokens=10)

    monkeypatch.setattr(fm, "generate_text", fake)
    with session_scope() as db:
        copy_, prov, _ = generate_listing_copy(db, prod["id"], None, "amazon", {})
    assert copy_["title"] == "Second try" and calls == [0.6, 0.3]


def test_translation_protects_brand_names():
    from app.services.growth import _protect, _restore

    texts, tok = _protect(["Hearth & Field Stoneware Mug", "Made by hearth & field"], ["Hearth & Field (demo)", "Hearth & Field"])
    assert all("Hearth" not in t and "hearth" not in t for t in texts) and tok
    # The model "translates" everything else but must leave the token alone.
    translated = [t.replace("Stoneware Mug", "Taza de gres").replace("Made by", "Hecho por") for t in texts]
    assert _restore(translated, tok) == ["Hearth & Field Taza de gres", "Hecho por Hearth & Field"]


def test_listing_with_string_keywords_is_served_as_list(client, prod):
    from app.db.models import Project
    from app.db.session import session_scope

    with session_scope() as db:
        p = Project(kind="listing", name="legacy", product_id=prod["id"],
                    data={"marketplace": "amazon", "copy": {"title": "T", "keywords": "a, b", "bullets": ["x"]}})
        db.add(p)
        db.flush()
        pid = p.id
    assert client.get(f"/api/listings/{pid}").json()["copy"]["keywords"] == ["a", "b"]
    assert "a, b" in client.get(f"/api/listings/{pid}/export?format=txt").text


# ---------------------------------------------------------------- team mode (runs last: toggles auth)
def test_team_mode_login_invite_roles(client):
    from tests.conftest import TestClient  # noqa: F401

    assert client.get("/api/auth/status").json()["team_mode"] is False
    owner = client.post("/api/auth/setup", json={"name": "Owner", "email": "owner@example.com", "password": "correct horse"})
    assert owner.status_code == 201
    assert client.get("/api/brands").status_code == 200  # owner session cookie set
    inv = client.post("/api/members", json={"email": "viewer@example.com", "role": "viewer"}).json()
    token = inv["invite_path"].split("token=")[1]
    client.post("/api/auth/logout")
    assert client.get("/api/brands").status_code == 401
    assert client.post("/api/auth/accept-invite", json={"token": token, "name": "Vi", "password": "viewer pass"}).status_code == 200
    assert client.get("/api/brands").status_code == 200
    assert client.post("/api/brands", json={"name": "Nope"}).status_code == 403
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"email": "owner@example.com", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "owner@example.com", "password": "correct horse"}).status_code == 200
    assert client.get("/api/health").status_code == 200
    # Turn team mode back off for any later tests.
    from app.db.models import Member
    from app.db.session import session_scope

    with session_scope() as db:
        for m in db.query(Member).all():
            db.delete(m)
    client.cookies.clear()
    assert client.get("/api/auth/status").json()["team_mode"] is False
