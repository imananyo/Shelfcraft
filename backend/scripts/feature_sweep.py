"""Exercise every Shelfcraft feature end-to-end with the REAL local models (no stubs).

Run against an isolated instance (see scripts\\test-instance.ps1), never your real workspace:
    .venv\\Scripts\\python.exe scripts\\feature_sweep.py --api http://127.0.0.1:8100 --out sweep.json
Writes a JSON report with every step's result and the pages it created (for the browser page check).
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import time
import zipfile
from typing import Any, Callable

import httpx
from PIL import Image, ImageDraw, ImageFont

ap = argparse.ArgumentParser()
ap.add_argument("--api", default="http://127.0.0.1:8100")
ap.add_argument("--out", default="sweep.json")
ap.add_argument("--only", default="", help="comma-separated step-name substrings")
A = ap.parse_args()
c = httpx.Client(base_url=f"{A.api}/api", timeout=120)
results: list[dict[str, Any]] = []
pages: list[str] = []
S: dict[str, Any] = {}  # shared ids between steps


def wait(job_id: str, limit: float = 1800) -> dict:
    t0 = time.time()
    while time.time() - t0 < limit:
        j = c.get(f"/jobs/{job_id}").json()
        if j["status"] in ("succeeded", "failed", "cancelled"):
            return j
        time.sleep(3)
    raise TimeoutError(f"job {job_id} still running after {limit}s")


def ok_job(job_id: str, limit: float = 1800) -> dict:
    j = wait(job_id, limit)
    assert j["status"] == "succeeded", f"job {j['type']} {j['status']}: {j.get('error')}"
    return j


def chk(r: httpx.Response, *codes: int) -> Any:
    codes = codes or (200, 201, 202, 204)
    assert r.status_code in codes, f"{r.request.method} {r.request.url.path} → HTTP {r.status_code}: {r.text[:300]}"
    ct = r.headers.get("content-type", "")
    return r.json() if "json" in ct and r.content else r


def raw(r: httpx.Response) -> httpx.Response:
    assert r.status_code < 400, f"{r.request.method} {r.request.url.path} → HTTP {r.status_code}: {r.text[:300]}"
    return r


def wait_batch(batch_id: str, limit: float = 3600) -> dict:
    t0 = time.time()
    while time.time() - t0 < limit:
        st = chk(c.get(f"/factory/batches/{batch_id}"))
        counts = st.get("counts") or {}
        finished = sum(v for k, v in counts.items() if k in ("succeeded", "failed", "cancelled"))
        if st.get("progress", 0) >= 1.0 or finished >= st.get("total", 1):
            st["status"] = "failed" if counts.get("failed") and not counts.get("succeeded") else ("partial" if counts.get("failed") else "succeeded")
            return st
        time.sleep(2)  # < uvicorn's 5 s keep-alive, avoids reusing a just-closed connection
    raise TimeoutError(f"batch {batch_id} still running after {limit}s")


def step(name: str, fn: Callable[[], Any]) -> None:
    if A.only and not any(s.strip().lower() in name.lower() for s in A.only.split(",")):
        return
    t0 = time.time()
    try:
        d = fn()
        res = {"name": name, "ok": True, "s": round(time.time() - t0), "detail": str(d)[:400]}
    except Exception as e:  # noqa: BLE001
        res = {"name": name, "ok": False, "s": round(time.time() - t0), "detail": f"{type(e).__name__}: {e}"[:800]}
    results.append(res)
    print(("PASS " if res["ok"] else "FAIL ") + f"[{res['s']:>4}s] {name} — {res['detail']}", flush=True)
    json.dump({"results": results, "pages": sorted(set(pages))}, open(A.out, "w"), indent=1)


def png(im: Image.Image, fmt: str = "PNG") -> bytes:
    b = io.BytesIO()
    im.save(b, fmt)
    return b.getvalue()


def font(size: int):
    for f in ("C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf"):
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def angle_photo(i: int) -> bytes:
    """A simple bottle-like object photographed from different angles (label shifts with rotation)."""
    im = Image.new("RGB", (800, 800), (236, 236, 232))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((300, 160, 500, 680), 60, fill=(40, 110, 140))
    d.rectangle((350, 110, 450, 170), fill=(30, 30, 30))
    x = 300 + (i * 40) % 160
    d.rectangle((x, 330, x + 60, 480), fill=(240, 200, 80))
    return png(im)


def text_image() -> bytes:
    im = Image.new("RGB", (1000, 1000), (250, 247, 240))
    d = ImageDraw.Draw(im)
    d.text((80, 80), "LEAKPROOF LID", font=font(64), fill=(20, 20, 20))
    d.text((80, 860), "Cold for 24 hours", font=font(48), fill=(40, 90, 80))
    d.ellipse((330, 250, 670, 760), fill=(200, 80, 60))
    return png(im)


def mask_for(w: int, h: int) -> str:
    m = Image.new("L", (w, h), 0)
    m.paste(255, (int(w * 0.05), int(h * 0.05), int(w * 0.22), int(h * 0.22)))
    return "data:image/png;base64," + base64.b64encode(png(m)).decode()


# ====================================================================== setup
prods = chk(c.get("/products"))["items"]
S["mug"] = next(p["id"] for p in prods if "Mug" in p["name"])
S["bottle"] = next(p["id"] for p in prods if "Bottle" in p["name"])
S["brand"] = chk(c.get("/brands"))[0]["id"] if isinstance(c.get("/brands").json(), list) else chk(c.get("/brands"))["items"][0]["id"]


# When re-running only some steps (--only), reuse objects created by an earlier run.
_ls = [x for x in chk(c.get("/listings")) if x.get("has_copy") and x.get("marketplace") == "amazon" and x["name"].count("—") == 1
       and "Mug" in x["name"]]  # not a translation
if _ls:
    S["listing"] = _ls[0]["id"]
_docs = chk(c.get("/documents"))
_docs = _docs["items"] if isinstance(_docs, dict) else _docs
if _docs:
    S["docs"] = [d["id"] for d in _docs[:3]]
S["lamp"] = next((p["id"] for p in prods if p["name"] == "Sweep Lamp"), S["bottle"])


def _photo(pid: str) -> dict:
    return chk(c.get("/assets", params={"product_id": pid, "source": "upload", "kind": "image"}))["items"][0]


# ====================================================================== system & dashboard
step("System: health, capabilities, dashboard, search, storage, usage, notifications", lambda: (
    chk(c.get("/health"))["status"], len(chk(c.get("/capabilities"))), bool(chk(c.get("/dashboard"))),
    len(chk(c.get("/search", params={"q": "mug"})).get("results", [])) if isinstance(c.get("/search", params={"q": "mug"}).json(), dict) else "list",
    bool(chk(c.get("/storage"))), bool(chk(c.get("/usage"))), bool(chk(c.post("/notifications/read-all")) is not None)))
pages += ["/", "/jobs", "/sessions", "/settings"]


# ====================================================================== brands
def brands():
    b = chk(c.post("/brands", json={"name": "Sweep Brand", "colors": ["#123456", "#f0c040"], "tone_of_voice": "warm, honest",
                                    "values": ["craft"], "aesthetic": ["minimal"], "tagline": "Made to last"}))
    chk(c.patch(f"/brands/{b['id']}", json={"tagline": "Built to last"}))
    logo = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    ImageDraw.Draw(logo).ellipse((20, 20, 280, 280), fill=(18, 52, 86, 255))
    chk(c.post(f"/brands/{b['id']}/logo", files={"file": ("logo.png", png(logo), "image/png")}))
    g = c.post(f"/brands/{b['id']}/guidelines", files={"file": ("guide.txt", b"Use warm, honest language. Never claim medical benefits.", "text/plain")},
               data={"title": "Voice guide"})
    chk(c.post(f"/brands/{b['id']}/activate"))
    chk(c.post(f"/brands/{S['brand']}/activate"))
    full = chk(c.get(f"/brands/{b['id']}"))
    S["brand2"] = b["id"]
    pages.append(f"/brands/{b['id']}")
    return f"logo={bool(full.get('logo_url') or full.get('logo_asset_id'))} guideline HTTP {g.status_code}"


step("Brands: create, edit, logo, guideline upload, activate", brands)
pages += ["/brands"]


# ====================================================================== products
def products():
    p = chk(c.post("/products", json={"name": "Sweep Lamp", "category": "Home", "features": ["Dimmable", "USB-C"], "price": 39.0,
                                      "brand_id": S["brand"], "variants": [{"name": "Black"}, {"name": "White"}]}))
    chk(c.patch(f"/products/{p['id']}", json={"description": "A small dimmable desk lamp."}))
    chk(c.post(f"/products/{p['id']}/images", files=[("files", ("lamp.png", angle_photo(0), "image/png"))]))
    dup = chk(c.post(f"/products/{p['id']}/duplicate"))
    chk(c.delete(f"/products/{dup['id']}"))
    csv_out = chk(c.get("/products/export.csv")).text
    imp = chk(c.post("/products/import.csv", files={"file": ("p.csv", b"name,sku,category,price,features\nCSV Kettle,CK-1,Kitchen,29.5,Fast boil|Auto off\n", "text/csv")}))
    paste = chk(c.post("/products/import-text", json={"text": "Acme Bamboo Board, Large\n$24.99\n• Organic bamboo\n• Juice groove\nMaterial: Bamboo\n"
                                                              "Made from sustainably harvested bamboo, gentle on knives and easy to clean."}))
    S["lamp"] = p["id"]
    pages.extend([f"/products/{p['id']}", f"/products/{paste['id']}"])
    return f"csv rows={csv_out.count(chr(10))} import={imp} paste={paste['name']!r}"


step("Products: create, edit, photo, duplicate, delete, CSV export/import, paste import", products)
pages += ["/products"]

step("Products: 360 angle-photo upload", lambda: (
    S.__setitem__("angles", chk(c.post(f"/products/{S['bottle']}/images/upload-angles",
                                       files=[("files", (f"a{i}.png", angle_photo(i), "image/png")) for i in range(6)], data={"title": "Spin set"}))),
    str(S["angles"])[:120])[1])


def research():
    j = ok_job(chk(c.post(f"/products/{S['mug']}/research", json={"reviews": "Love the glaze. Handle is comfy. Wish it held more coffee. Chipped after a month."}))["id"])
    r = chk(c.get(f"/products/{S['mug']}/research"))[0]
    return f"{r['provider']}/{r['model']} keys={sorted(r['result'])[:8]}"


step("Product research (Ollama)", research)


# ====================================================================== listings
def listing():
    lst = chk(c.post("/listings", json={"product_id": S["mug"], "marketplace": "amazon", "keywords": "stoneware mug, coffee cup"}))
    ok_job(chk(c.get(f"/listings/{lst['id']}"))["jobs"][0]["id"])
    full = chk(c.get(f"/listings/{lst['id']}"))
    cp = full["copy"]
    assert cp.get("title") and len(cp.get("bullets") or []) >= 3, f"incomplete copy: {list(cp)}"
    assert isinstance(cp.get("keywords", []), list) and isinstance(cp.get("bullets"), list)
    S["listing"] = lst["id"]
    pages.append(f"/listings/{lst['id']}")
    pages.append(f"/listings/{lst['id']}?tab=strategy")
    return f"{full['provenance']['provider']} · {cp['title'][:70]!r} · {len(cp['bullets'])} bullets · {len(cp.get('keywords') or [])} kw · warnings={len(full['warnings'])}"


step("Listing: generate copy (Ollama)", listing)


def listing_edit():
    L = chk(c.get(f"/listings/{S['listing']}"))
    cp = {**L["copy"], "title": L["copy"]["title"] + " Gift"}
    chk(c.put(f"/listings/{S['listing']}/copy", json={"copy": cp, "save_version": True}))
    ok_job(chk(c.post(f"/listings/{S['listing']}/generate", json={"field": "title", "instruction": "shorter"}))["id"])
    vers = chk(c.get(f"/listings/{S['listing']}/versions"))
    chk(c.post(f"/listings/{S['listing']}/restore/0"))
    exports = {f: len(raw(c.get(f"/listings/{S['listing']}/export", params={"format": f})).content) for f in ("txt", "csv", "json")}
    return f"versions={len(vers)} exports={exports}"


step("Listing: edit, regenerate title, versions, restore, export TXT/CSV/JSON", listing_edit)


def other_marketplaces():
    out = []
    for mk in ("shopify", "amazon_mobile"):
        lst = chk(c.post("/listings", json={"product_id": S["bottle"], "marketplace": mk}))
        ok_job(chk(c.get(f"/listings/{lst['id']}"))["jobs"][0]["id"])
        pages.append(f"/listings/{lst['id']}")
        out.append(f"{mk}:{chk(c.get(f'/listings/{lst['id']}'))['copy']['title'][:40]!r}")
    return " ".join(out)


step("Listing: Shopify + Amazon mobile", other_marketplaces)


def translate():
    j = ok_job(chk(c.post(f"/listings/{S['listing']}/translate", json={"language": "es", "country": "ES", "translate_images": False}))["id"])
    t = chk(c.get(f"/listings/{j['result']['project_id']}"))
    pages.append(f"/listings/{t['id']}")
    assert isinstance(t["copy"].get("keywords", []), list)
    return f"ES title: {t['copy']['title'][:70]!r}"


step("Listing: translate to Spanish", translate)


def grader():
    g = chk(c.post("/grader", json={"listing_id": S["listing"]}))
    g2 = chk(c.post("/grader", json={"title": "BEST mug!!!", "bullets": ["good"], "description": "mug", "ai_review": True}))
    return f"listing score={g['score']} · bad={g2['score']} · ai={'ai' in json.dumps(g2).lower()}"


step("Listing grader: rule-based + AI review", grader)
pages += ["/grader", "/listings", "/listings/new", "/create"]


def listing_images():
    j = ok_job(chk(c.post(f"/listings/{S['listing']}/images", json={"style": "natural"}))["id"], 3600)
    full = chk(c.get(f"/listings/{S['listing']}"))
    assert full["images"], f"no images; errors={full['image_errors']}"
    return f"{len(full['images'])} images · slots={[i['slot'] for i in full['images']]} · errors={full['image_errors']}"


step("Listing: full image set (rembg + SD-Turbo + templates)", listing_images)


def bulk_copy():
    j = chk(c.post("/listings/bulk", json={"product_ids": [S["bottle"], S["lamp"]]}))
    st = wait_batch(j["batch_id"])
    assert st["status"] not in ("failed",), st
    return f"batch {st['status']} · counts={st.get('counts')}"


step("Labs: Title & Bullets bulk (2 products)", bulk_copy)
pages += ["/labs", "/labs/title-bullets", "/labs/packaging"]


# ====================================================================== image studio
def creatives():
    out = {}
    types = list(chk(c.get("/creative/options"))["creative_types"])
    for t in types:
        s = chk(c.post("/creative/generate", json={"creative_type": t, "product_id": S["mug"], "brand_id": S["brand"], "style": "minimal"}))
        j = wait(s["jobs"][0]["id"], 1200)
        out[t] = "ok" if j["status"] == "succeeded" else f"FAIL {j.get('error')}"
        if j["status"] == "succeeded":
            S.setdefault("creatives", {})[t] = j["result"]
            if j["result"].get("document_id"):
                S.setdefault("docs", []).append(j["result"]["document_id"])
        S["session"] = s.get("id") or s.get("session_id")
    bad = {k: v for k, v in out.items() if v != "ok"}
    assert not bad, bad
    return f"{len(out)} creative types ok"


step("Image studio: every creative type (14)", creatives)
pages += ["/studio", "/library", "/projects"]


def edits():
    src = _photo(S["mug"])
    ops = chk(c.get("/creative/options"))["edit_operations"]
    out = {}
    for op, meta in ops.items():
        body: dict[str, Any] = {"asset_id": src["id"], "operation": op}
        if meta["needs_mask"]:
            body["mask"] = mask_for(src["width"], src["height"])
        if op == "generative_fill":
            body["prompt"] = "a small green plant"
        if op == "replace_background":
            body.update(background_mode="prompt", prompt="marble kitchen counter, soft daylight")
        if op == "extend":
            body.update(width=int(src["width"] * 1.5), height=src["height"])
        if op == "recolor":
            body["color"] = "#2f6f67"
        r = c.post("/edits", json=body)
        if r.status_code >= 400:
            out[op] = f"HTTP {r.status_code}: {r.text[:150]}"
            continue
        j = wait(r.json()["id"], 1200)
        out[op] = "ok" if j["status"] == "succeeded" else f"FAIL {j.get('error')}"
        if op == "remove_object" and j["status"] == "succeeded":
            S["edited_asset"] = (j["result"].get("asset_ids") or [j["result"].get("asset_id")])[0]
    bad = {k: v for k, v in out.items() if v != "ok"}
    assert not bad, bad
    return f"{len(out)} edit operations ok"


step("Spot edit: every operation (8)", edits)
pages += ["/edit"]


def inspire():
    ref = chk(c.post("/assets", files=[("files", ("ref.png", text_image(), "image/png"))]))
    ref_id = (ref if isinstance(ref, list) else ref.get("items", ref.get("assets", [ref])))[0]["id"]
    an = chk(c.post("/inspire/analyze", json={"asset_id": ref_id}))
    j = ok_job(chk(c.post("/inspire/generate", json={"reference_asset_id": ref_id, "product_id": S["mug"]}))["id"], 1200)
    S["ref_asset"] = ref_id
    return f"analysis keys={sorted(an)[:6]} · result={list(j['result'])[:5]}"


step("Steal the look: analyze reference + generate", inspire)
pages += ["/inspire"]


# ====================================================================== editor / documents / templates / projects
def documents():
    d = chk(c.post("/documents", json={"name": "Sweep design", "width": 1200, "height": 1200}))
    full = chk(c.get(f"/documents/{d['id']}"))
    doc = full["document"]
    doc.setdefault("layers", []).append({"id": "t1", "type": "text", "text": "Hello", "x": 100, "y": 100, "fontSize": 64, "fill": "#222"})
    chk(c.put(f"/documents/{d['id']}", json={"document": doc, "base_version": full.get("version"), "checkpoint": True, "thumbnail": True}))
    conflict = c.put(f"/documents/{d['id']}", json={"document": doc, "base_version": 0})
    revs = chk(c.get(f"/documents/{d['id']}/revisions"))
    sizes = {f: len(raw(c.get(f"/documents/{d['id']}/export", params={"format": f})).content) for f in ("png", "jpeg", "json")}
    imp = chk(c.post("/documents/import", json=raw(c.get(f"/documents/{d['id']}/export", params={"format": "json"})).json()))
    t = chk(c.post("/templates", json={"name": "Sweep template", "document_id": d["id"]}))
    chk(c.get(f"/templates/{t['id']}"))
    pr = chk(c.post("/projects", json={"name": "Sweep project", "kind": "design", "product_id": S["mug"]}))
    chk(c.post(f"/projects/{pr['id']}/duplicate"))
    z = raw(c.post(f"/projects/{pr['id']}/export.zip"))
    S["doc"] = d["id"]
    pages.extend([f"/editor/{d['id']}", f"/projects/{pr['id']}"])
    return f"conflict HTTP {conflict.status_code} · revisions={len(revs)} · export bytes={sizes} · import={imp.get('id')} · zip={len(z.content)}"


step("Editor: document save, version conflict, revisions, PNG/JPEG/JSON export, import, template, project", documents)
pages += ["/projects"]


def apply_design():
    docs = (S.get("docs") or [S.get("doc")])[:1]
    j = chk(c.post("/scale/apply", json={"document_ids": docs, "product_ids": [S["bottle"]]}))
    res = j["results"]
    assert res and all(r.get("asset_id") for r in res), j
    for r in res:
        pages.append(f"/editor/{r['document_id']}")
    return f"applied {len(docs)} design(s) → bottle · {len(res)} new designs rendered"


step("Scale: apply a design to another product", apply_design)
pages += ["/scale"]


def decompose():
    a = chk(c.post("/assets", files=[("files", ("txt.png", text_image(), "image/png"))]))
    aid = (a if isinstance(a, list) else a.get("items", a.get("assets", [a])))[0]["id"]
    j = ok_job(chk(c.post(f"/assets/{aid}/decompose"))["id"], 1200)
    did = j["result"].get("document_id")
    if did:
        pages.append(f"/editor/{did}")
    return f"result={ {k: v for k, v in j['result'].items() if k != 'layers'} }"


step("Image → editable layers (OCR + cut-out + LaMa)", decompose)


# ====================================================================== A+
def aplus():
    mods = list(chk(c.get("/aplus/modules"))["modules"])
    out = []
    for tier in ("premium", "basic", "mobile"):
        a = chk(c.post("/aplus", json={"name": f"Sweep A+ {tier}", "product_id": S["mug"], "tier": tier, "modules": mods[:6]}))
        chk(c.post(f"/aplus/{a['id']}/modules", json={"type": mods[6] if len(mods) > 6 else "detail"}))
        over = c.post(f"/aplus/{a['id']}/modules", json={"type": "detail"})  # 8th module must be refused
        assert over.status_code == 422, f"8th module not refused: {over.status_code}"
        full = chk(c.get(f"/aplus/{a['id']}"))
        prev = raw(c.get(f"/aplus/{a['id']}/preview.png"))
        z = zipfile.ZipFile(io.BytesIO(raw(c.post(f"/aplus/{a['id']}/export.zip")).content))
        pages.append(f"/aplus/{a['id']}")
        out.append(f"{tier}: {len(full.get('modules', []))} modules, {len([n for n in z.namelist() if n.endswith('.jpg')])} jpgs, preview {len(prev.content)}B")
    return " | ".join(out)


step("A+ content: all modules × premium/basic/mobile, preview, ZIP", aplus)
pages += ["/aplus", "/aplus/new"]


# ====================================================================== factory
def factory():
    body = {"name": "Sweep factory", "product_ids": [S["mug"], S["bottle"]], "creative_types": ["white_bg_main", "feature", "listing_copy"]}
    prev = chk(c.post("/factory/preview", json=body))
    b = chk(c.post("/factory/batches", json=body))
    st = wait_batch(b["id"])
    z = raw(c.get(f"/factory/batches/{b['id']}/download"))
    pages.append(f"/factory?run={b['id']}")
    assert st["status"] == "succeeded", st.get("counts")
    return f"preview={ {k: prev[k] for k in list(prev)[:3]} } status={st.get('status')} counts={st.get('counts')} zip HTTP {z.status_code} {len(z.content)}B"


step("Factory: 2 products × (white bg, feature, listing copy) + ZIP", factory)
pages += ["/factory"]


# ====================================================================== video
def videos():
    v = chk(c.post("/videos", json={"name": "Sweep reel", "product_id": S["mug"], "aspect": "9:16", "target_duration": 8}))
    chk(c.patch(f"/videos/{v['id']}", json={"transition": "fade"}))
    j = ok_job(chk(c.post(f"/videos/{v['id']}/render"))["id"])
    vo = ok_job(chk(c.post(f"/videos/{v['id']}/voiceover", json={"voice": chk(c.get("/voices"))[0]}))["id"])
    pages.append(f"/videos/{v['id']}")
    return f"render {j['result'].get('duration_s')}s · voiceover {vo['result'].get('lines')} lines {vo['result'].get('duration_s')}s"


step("Video: storyboard render + offline voiceover", videos)


def spin():
    imgs = chk(c.get("/assets", params={"product_id": S["bottle"], "kind": "image"}))["items"]
    ids = [a["id"] for a in imgs if "a" in (a.get("filename") or "")][:6] or [a["id"] for a in imgs][:6]
    assert len(ids) >= 3, f"only {len(ids)} angle photos"
    j = ok_job(chk(c.post("/videos/spin", json={"asset_ids": ids, "title": "Sweep spin"}))["id"], 1800)
    return f"{j['result']}"


step("Video: 360° spin from angle photos", spin)
pages += ["/videos", "/videos/new", "/videos/spin"]


# ====================================================================== ads & packaging
def ads():
    out = []
    for fmt in ("sb_image", "story_ad"):
        a = chk(c.post("/ads", json={"product_id": S["mug"], "format": fmt, "count": 3}))
        ok_job(a["job"]["id"])
        d = chk(c.get(f"/ads/{a['id']}"))
        r = chk(c.post(f"/ads/{a['id']}/render", json={"indices": [0]}))
        for x in r["jobs"]:
            ok_job(x["id"], 1200)
        pages.append(f"/ads/{a['id']}")
        out.append(f"{fmt}: {len(d['concepts'])} concepts, rendered {len(r['jobs'])}")
    return " | ".join(out)


step("Ads studio: image + video formats, concepts + render", ads)
pages += ["/ads", "/ads/new"]


def packaging():
    j = ok_job(chk(c.post("/labs/packaging", json={"product_id": S["mug"], "count": 4}))["id"])
    pid = j["result"]["project_id"]
    ok_job(chk(c.post(f"/labs/packaging/{pid}/render/0"))["id"], 1200)
    d = chk(c.get(f"/labs/packaging/{pid}"))
    pages.append(f"/labs/packaging?project={pid}")
    return f"{len(d['concepts'])} concepts · renders={len(d.get('render_urls') or {})}"


step("Packaging ideas + render", packaging)


# ====================================================================== playbooks
def playbooks():
    lib = chk(c.get("/playbooks", params={"templates": "true"}))
    assert len(lib) >= 5, f"template library has {len(lib)} playbooks"
    imported = chk(c.post(f"/playbooks/{lib[0]['id']}/import"))
    mine = chk(c.post("/playbooks", json={"name": "Sweep playbook", "steps": [{"kind": "creative", "creative_type": "white_bg_main"},
                                                                               {"kind": "creative", "creative_type": "feature"}]}))
    chk(c.put(f"/playbooks/{mine['id']}", json={"name": "Sweep playbook 2", "steps": mine["steps"]}))
    assert c.put(f"/playbooks/{lib[0]['id']}", json={"name": "x", "steps": mine["steps"]}).status_code == 422, "template editable"
    run = chk(c.post(f"/playbooks/{mine['id']}/run", json={"product_ids": [S["bottle"]]}))
    st = wait_batch(run["batch_id"])
    assert st["status"] == "succeeded", st.get("counts")
    pages.extend([f"/playbooks/{mine['id']}", f"/playbooks/{imported['id']}"])
    return f"library={len(lib)} templates · imported {imported['name']!r} · run {st['status']} {st.get('counts')}"


step("Playbooks: create, edit, run", playbooks)
pages += ["/playbooks"]


# ====================================================================== library
def library():
    items = chk(c.get("/assets", params={"limit": 50}))["items"]
    a = items[0]
    chk(c.patch(f"/assets/{a['id']}", json={"favorite": True, "tags": ["sweep"]}))
    f = chk(c.post("/assets/folders", json={"name": "Sweep folder"}))
    chk(c.patch(f"/assets/{a['id']}", json={"folder_id": f["id"]}))
    chk(c.patch(f"/assets/folders/{f['id']}", json={"name": "Sweep folder 2"}))
    z = chk(c.post("/assets/zip", json={"asset_ids": [x["id"] for x in items[:3]]}))
    conv = chk(c.get(f"/assets/{a['id']}/convert", params={"format": "webp"}))
    thumb = chk(c.get(f"/assets/{a['id']}/thumb"))
    file_ = chk(c.get(f"/assets/{a['id']}/file"))
    return f"{len(items)} assets · zip {len(z.content)}B · webp {len(conv.content)}B · thumb {len(thumb.content)}B · file {len(file_.content)}B"


step("Library: favorite, tag, folders, ZIP, convert, thumb, file", library)


# ====================================================================== public API + MCP
def public_api():
    k = chk(c.post("/api-keys", json={"name": "sweep", "scopes": ["read", "write"]}))
    h = {"Authorization": f"Bearer {k['key']}"}
    v1 = httpx.Client(base_url=f"{A.api}/v1", headers=h, timeout=60)
    prods = chk(v1.get("/products"))
    spec = chk(httpx.get(f"{A.api}/v1/openapi.json"))
    os.environ["SHELFCRAFT_API_URL"], os.environ["SHELFCRAFT_API_KEY"] = A.api, k["key"]
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    import importlib

    import mcp_server
    importlib.reload(mcp_server)
    tools = mcp_server.list_products("")
    g = mcp_server.grade_listing(listing_id=S.get("listing"))
    chk(c.delete(f"/api-keys/{k['id']}"))
    assert v1.get("/products").status_code == 401
    return f"/v1 products={len(prods if isinstance(prods, list) else prods.get('items', []))} · {len(spec['paths'])} paths · MCP list={len(tools)} grade={g['score']}"


step("Public API /v1 + MCP server tools + key revoke", public_api)


# ====================================================================== providers, settings, jobs, backups
def system_admin():
    prov = chk(c.get("/providers"))
    t = chk(c.post("/providers/ollama/test"))
    s = chk(c.patch("/settings", json={"generation_defaults": {"aspect": "1:1", "image_size": 1024, "language": "en"}}))
    jobs = chk(c.get("/jobs", params={"limit": 200}))
    jl = jobs["items"] if isinstance(jobs, dict) else jobs
    failed = [j for j in jl if j["status"] == "failed"]
    b = chk(c.post("/backups"))
    lst = chk(c.get("/backups"))
    return f"providers={len(prov)} ollama test={t.get('ok')} · jobs={len(jl)} failed={[(j['type'], j['error']) for j in failed][:5]} · backups={len(lst)}"


step("Providers test, settings, jobs list, backup", system_admin)

print("\nSUMMARY")
for r in results:
    print(f"{'PASS' if r['ok'] else 'FAIL'} | {r['s']:>5}s | {r['name']}")
print(f"{sum(r['ok'] for r in results)}/{len(results)} passed")
sys.exit(0 if all(r["ok"] for r in results) else 1)
