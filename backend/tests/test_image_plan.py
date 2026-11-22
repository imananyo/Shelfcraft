"""Analyse → plan → render: creative brief reuse, per-slot image plan, brand rules and per-image render jobs."""
from __future__ import annotations

import json

import pytest

from app.ai import fallback_manager as fm
from app.ai.base import TextResult
from tests.conftest import make_png, run_pending_jobs

RESEARCH = {"summary": "s", "positioning": "The bottle for long trails", "usps": ["24h cold", "340 g light"],
            "pain_points": ["Warm water by noon", "Leaky lids"], "personas": [{"name": "Day hiker", "pain_points": ["heavy pack"]}],
            "marketing_angles": [{"angle": "Cold all day", "hook": "Still ice-cold at the summit"}],
            "creative_strategy": {"main_image": "bottle upright", "lifestyle": "summit rock at sunrise, backpack nearby",
                                  "infographics": ["insulation layers"], "video": "pour"},
            "review_sentiment": {"overall": "no data"}, "assumptions": []}
COPY = {"title": "Trailhead Steel Bottle", "bullets": ["COLD: 24h", "LEAKPROOF: cap", "LIGHT: 340 g", "WIDE: mouth", "STEEL: 18/8"],
        "description": "d", "keywords": ["bottle"], "search_terms": "flask", "headline": "Built for the trail",
        "image_strategy": [{"slot": "comparison", "concept": "c", "headline": "Old copy headline", "callouts": ["x"]}]}
BRIEF = {"hook": "Still ice-cold at the summit", "creative_concept": "Sunrise summits", "target": "Day hikers",
         "customer_needs": [{"feature": "Double-wall steel", "functional_benefit": "24h cold", "emotional_benefit": "Earned refreshment",
                             "problem_solved": "Warm water by noon"}]}
CALLS: list[str] = []
PROMPTS: dict[str, str] = {}


def _slot_json(purpose: str) -> dict:
    slot = purpose.removeprefix("image_plan_")
    if slot == "lifestyle":  # this one breaks a brand rule -> must fall back
        return {"purpose": "p", "concept": "trail", "headline": "Guaranteed cold forever", "callouts": [], "strategy_source": "hook"}
    return {"purpose": f"show {slot}", "concept": f"{slot} scene on a granite rock at sunrise with soft light",
            "headline": "One two three four five six seven eight nine ten",
            "callouts": ["Invented eco claim", "Double-wall steel", "Leakproof cap", "24h cold", "340 g light"],
            "people": slot == "lifestyle_2", "strategy_source": "pain_point", "strategy_note": "model's own pick (ignored)"}


@pytest.fixture
def llm(monkeypatch):
    def fake(req, *, purpose, preferred=None, strict=False):
        CALLS.append(purpose)
        PROMPTS[purpose] = req.prompt
        if purpose == "product_research":
            data = RESEARCH
        elif purpose == "creative_brief":
            data = BRIEF
        elif purpose.startswith("image_plan_"):
            data = _slot_json(purpose)
        elif purpose == "brand_rules":
            data = {"safe_claims": ["Keeps drinks cold"], "banned_words": ["guaranteed", "guaranteed"], "photo_look": "warm sunrise",
                    "props_allowed": "rocks, backpack", "headline_max_words": 99}
        else:
            data = COPY
        return TextResult(text=json.dumps(data), provider="fake", model="fake-1")

    monkeypatch.setattr(fm, "generate_text", fake)
    CALLS.clear()
    return CALLS


@pytest.fixture(scope="module")
def setup(client):
    b = client.post("/api/brands", json={"name": "Summit", "colors": ["#14532d"]}).json()
    client.patch(f"/api/brands/{b['id']}", json={"rules": {"banned_words": ["guaranteed"], "headline_max_words": 5,
                                                           "callouts_max": 3, "photo_look": "warm sunrise light"}})
    p = client.post("/api/products", json={"name": "Summit Bottle", "brand_id": b["id"], "category": "Outdoor",
                                           "features": ["Double-wall steel", "Leakproof cap"], "benefits": ["Cold for 24h"],
                                           "specifications": {"Height": "25 cm", "Weight": "340 g"}}).json()
    client.post(f"/api/products/{p['id']}/images", files=[("files", ("p.png", make_png(500, 500), "image/png"))])
    return {"brand": b, "product": p}


def _listing(client, setup) -> str:
    lst = client.post("/api/listings", json={"product_id": setup["product"]["id"], "marketplace": "amazon"}).json()
    run_pending_jobs()
    return lst["id"]


def test_brand_rules_are_cleaned_saved_and_used_in_prompts(client, setup, llm):
    b = client.get(f"/api/brands/{setup['brand']['id']}").json()
    assert b["rules"]["banned_words"] == ["guaranteed"] and b["rules"]["headline_max_words"] == 5
    # AI draft is returned by the job, not saved.
    r = client.post(f"/api/brands/{setup['brand']['id']}/rules/draft")
    assert r.status_code == 202
    assert run_pending_jobs() == ["succeeded"]
    job = client.get(f"/api/jobs/{r.json()['id']}").json()
    rules = job["result"]["rules"]
    assert rules["banned_words"] == ["guaranteed"] and rules["props_allowed"] == ["rocks", "backpack"]
    assert rules["headline_max_words"] == 12 and rules["ai_drafted"] is True  # clamped to the allowed range
    assert client.get(f"/api/brands/{setup['brand']['id']}").json()["rules"]["photo_look"] == "warm sunrise light"
    # Copy prompts now carry the brand rules.
    lid = _listing(client, setup)
    assert "Never use these words/claims: guaranteed" in PROMPTS["listing_copy"]
    assert client.get(f"/api/listings/{lid}").json()["copy"]["title"]


def test_listing_copy_gets_deep_strategy_image_ideas(client, setup, llm):
    client.post(f"/api/products/{setup['product']['id']}/research", json={})
    run_pending_jobs()
    _listing(client, setup)
    assert "summit rock at sunrise" in PROMPTS["listing_copy"] and "creative_strategy ideas" in PROMPTS["listing_copy"]


def test_plan_uses_brief_and_rules_and_reuses_brief(client, setup, llm):
    lid = _listing(client, setup)
    assert client.post(f"/api/listings/{lid}/plan", json={}).status_code == 202
    assert run_pending_jobs() == ["succeeded"]
    full = client.get(f"/api/listings/{lid}").json()
    plan, brief = full["image_plan"], full["brief"]
    assert brief["hook"] == "Still ice-cold at the summit" and brief["stale"] is False
    assert brief["strategy"]["creative_strategy"]["lifestyle"].startswith("summit rock")  # Deep Strategy ideas kept
    slots = {s["slot"]: s for s in plan["slots"]}
    assert list(slots) == ["main_white", "lifestyle", "infographic_features", "infographic_benefits", "comparison",
                           "dimensions", "detail"]
    assert "Still ice-cold at the summit" in PROMPTS["image_plan_detail"] and "warm sunrise light" in PROMPTS["image_plan_detail"]
    assert "infographic_features:" in PROMPTS["image_plan_detail"]  # earlier slots are passed on to avoid repeats
    main = slots["main_white"]
    assert main["headline"] == "" and main["callouts"] == [] and main["source"] == "auto" and "image_plan_main_white" not in llm
    dims = slots["dimensions"]  # measurements come straight from the specs, no AI
    assert dims["source"] == "auto" and dims["callouts"] == ["Height: 25 cm", "Weight: 340 g"]
    feat = slots["infographic_features"]
    assert feat["headline"] == "One two three four five"  # brand limit: 5 words
    assert feat["callouts"] == ["Double-wall steel", "Leakproof cap", "24h cold"]  # invented claim dropped, max 3
    assert feat["strategy_source"] == "usp" and feat["strategy_note"] == "24h cold" and feat["provider"] == "fake"
    # Shelfcraft assigns each image its own strategy point (the model's own pick is ignored).
    notes = [s["strategy_note"] for k, s in slots.items() if k != "main_white"]
    assert len(set(notes)) == len(notes) and slots["comparison"]["strategy_source"] == "pain_point"
    assert "This image must prove this point: 24h cold" in PROMPTS["image_plan_infographic_features"]
    life = slots["lifestyle"]  # AI used a banned word -> fallback from the brief
    assert life["source"] == "fallback" and not life["flags"] and "guaranteed" not in life["headline"].lower()
    # Second plan: nothing changed -> same brief, no new brief AI call.
    n_brief = llm.count("creative_brief")
    client.post(f"/api/listings/{lid}/plan", json={})
    run_pending_jobs()
    assert client.get(f"/api/listings/{lid}").json()["brief"]["id"] == brief["id"] and llm.count("creative_brief") == n_brief
    # New Deep Strategy -> brief is stale and rebuilt on the next plan.
    client.post(f"/api/products/{setup['product']['id']}/research", json={})
    run_pending_jobs()
    assert client.get(f"/api/listings/{lid}").json()["brief"]["stale"] is True
    client.post(f"/api/listings/{lid}/plan", json={})
    run_pending_jobs()
    assert client.get(f"/api/listings/{lid}").json()["brief"]["id"] != brief["id"]


def test_plan_falls_back_without_ai(client, setup, monkeypatch):
    from app.ai.base import NoProviderAvailable

    lid = _listing(client, setup)

    def down(req, *, purpose, preferred=None, strict=False):
        raise NoProviderAvailable("text", [])

    monkeypatch.setattr(fm, "generate_text", down)
    client.post(f"/api/listings/{lid}/plan", json={"rebuild_brief": True})
    assert run_pending_jobs() == ["succeeded"]
    full = client.get(f"/api/listings/{lid}").json()
    assert full["brief"]["ai_pass"] is False and "non-AI" in full["brief"]["model"]
    slots = {s["slot"]: s for s in full["image_plan"]["slots"]}
    assert {s["source"] for s in slots.values()} == {"fallback", "auto"}
    assert slots["dimensions"]["callouts"][:2] == ["Height: 25 cm", "Weight: 340 g"]


def test_edit_plan_flags_banned_words_and_rejects_unknown_slot(client, setup, llm):
    lid = _listing(client, setup)
    client.post(f"/api/listings/{lid}/plan", json={})
    run_pending_jobs()
    slots = client.get(f"/api/listings/{lid}").json()["image_plan"]["slots"]
    slots[1] = {**slots[1], "headline": "Guaranteed to impress"}
    r = client.put(f"/api/listings/{lid}/plan", json={"slots": slots})
    assert r.status_code == 200, r.text
    edited = r.json()["image_plan"]
    assert edited["edited_by_user"] and edited["slots"][1]["source"] == "user"
    assert edited["slots"][1]["flags"] == ["uses banned word “guaranteed”"]
    assert edited["slots"][0]["source"] == "auto" and edited["slots"][2]["source"] == "ai"  # untouched slots keep their origin
    assert client.put(f"/api/listings/{lid}/plan", json={"slots": [{"slot": "nope"}]}).status_code == 422


def test_image_set_renders_one_job_per_slot_and_retries_one(client, setup, llm, monkeypatch):
    import app.services.creative as creative

    lid = _listing(client, setup)
    real = creative.generate_creative

    def flaky(db, **kw):
        if kw["creative_type"] == "comparison":
            raise ValueError("template broke")
        return real(db, **kw)

    monkeypatch.setattr(creative, "generate_creative", flaky)
    r = client.post(f"/api/listings/{lid}/images", json={"slots": ["main_white", "comparison", "dimensions"]})
    assert r.status_code == 202
    assert run_pending_jobs() == ["succeeded", "succeeded", "failed", "succeeded"]
    full = client.get(f"/api/listings/{lid}").json()
    assert [i["slot"] for i in full["images"]] == ["main_white", "dimensions"]
    st = full["image_status"]
    assert st["main_white"]["status"] == "done" and st["comparison"]["status"] == "failed"
    assert full["image_errors"] == ["comparison: template broke"]
    assert all(j["type"] != "listing_image_slot" for j in full["jobs"])
    # Retry only the failed image.
    monkeypatch.setattr(creative, "generate_creative", real)
    assert client.post(f"/api/listings/{lid}/images/comparison/retry", json={}).status_code == 202
    assert run_pending_jobs() == ["succeeded"]
    full = client.get(f"/api/listings/{lid}").json()
    assert [i["slot"] for i in full["images"]] == ["main_white", "comparison", "dimensions"]  # plan order
    assert full["image_status"]["comparison"]["status"] == "done" and full["image_errors"] == []
    assert client.post(f"/api/listings/{lid}/images/bogus/retry", json={}).status_code == 404


def test_small_model_safeguards():
    from app.services.brand_rules import clean_rules
    from app.services.image_plan import grounded, strip_echo

    assert strip_echo("one sentence: Stays cold all day") == "Stays cold all day"
    assert strip_echo("Max 30 words: granite rock") == "granite rock" and strip_echo("Plain text") == "Plain text"
    corpus = "double-wall steel keeps drinks cold for 24h. 340 g"
    assert grounded("24h cold", corpus) and grounded("Steel body", corpus) and not grounded("Eco-Friendly", corpus)
    r = clean_rules({"props_allowed": ["rocks", "Gym"], "props_banned": ["gym"], "safe_claims": ["best"], "banned_words": ["Best"]})
    assert r["props_allowed"] == ["rocks"] and r["safe_claims"] == []
    from app.services.image_plan import strip_product_name

    name = "Garnier Men Oil Clear Clay D-Tox Icy Face Wash 155 g"
    assert strip_product_name("Men Oil Clear Clay D-Tox Icy Face Wash in a modern, clean bathroom", name) == "in a modern, clean bathroom"
    assert strip_product_name("Cool morning light on a wet sink", name) == "Cool morning light on a wet sink"
    assert strip_product_name("Bright sink , Men Oil Clear tube, soft light", name) == "Bright sink, tube, soft light"
