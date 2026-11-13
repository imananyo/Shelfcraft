"""Real end-to-end smoke run against a running backend using the actual local AI models.

Usage: .venv\\Scripts\\python.exe scripts\\e2e_real.py [--api http://127.0.0.1:8000] [--product <id>]
Prints timings and provider attribution for each step; exits non-zero if any step fails.
"""
from __future__ import annotations

import argparse
import base64
import io
import sys
import time

import httpx
from PIL import Image

results: list[tuple[str, bool, str]] = []


def wait(c: httpx.Client, job_id: str, timeout: float = 1200) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = c.get(f"/jobs/{job_id}").json()
        if j["status"] in ("succeeded", "failed", "cancelled"):
            return j
        time.sleep(3)
    raise TimeoutError(job_id)


def step(name: str):
    def deco(fn):
        def run(*a, **k):
            t0 = time.time()
            try:
                detail = fn(*a, **k)
                results.append((name, True, f"{time.time() - t0:.0f}s · {detail}"))
            except Exception as e:  # noqa: BLE001
                results.append((name, False, f"{time.time() - t0:.0f}s · {type(e).__name__}: {e}"))
            print(("PASS " if results[-1][1] else "FAIL ") + name + " — " + results[-1][2], flush=True)
        return run
    return deco


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--product")
    a = ap.parse_args()
    c = httpx.Client(base_url=f"{a.api}/api", timeout=60)
    pid = a.product or next(p["id"] for p in c.get("/products").json()["items"] if "Mug" in p["name"])

    @step("Listing copy via Ollama (local LLM)")
    def listing():
        lst = c.post("/listings", json={"product_id": pid, "marketplace": "amazon"}).json()
        job = next(j for j in c.get(f"/listings/{lst['id']}").json()["jobs"])
        j = wait(c, job["id"])
        assert j["status"] == "succeeded", j.get("error")
        full = c.get(f"/listings/{lst['id']}").json()
        cp = full["copy"]
        assert cp["title"] and len(cp["bullets"]) >= 3, "copy incomplete"
        return f"{full['provenance']['provider']}/{full['provenance']['model']} · title: {cp['title'][:80]!r} · {len(cp['bullets'])} bullets"

    @step("Product research via Ollama")
    def research():
        j = wait(c, c.post(f"/products/{pid}/research", json={"reviews": "Love the glaze. Handle is comfy. Wish it were bigger."}).json()["id"])
        assert j["status"] == "succeeded", j.get("error")
        r = c.get(f"/products/{pid}/research").json()[0]
        return f"{r['provider']}/{r['model']} · {len(r['result'].get('personas', []))} personas · sentiment={r['result'].get('review_sentiment', {}).get('overall')}"

    @step("White-background main image (rembg)")
    def white():
        s = c.post("/creative/generate", json={"creative_type": "white_bg_main", "product_id": pid, "width": 2000, "height": 2000}).json()
        j = wait(c, s["jobs"][0]["id"])
        assert j["status"] == "succeeded", j.get("error")
        a_ = c.get(f"/assets/{j['result']['asset_ids'][0]}").json()
        return f"{a_['provider']} · {a_['width']}×{a_['height']}"

    @step("Lifestyle image with AI background (local SD-Turbo) + untouched product")
    def lifestyle():
        s = c.post("/creative/generate", json={"creative_type": "lifestyle", "product_id": pid, "width": 1024, "height": 1024,
                                               "extra_prompt": "rustic wooden kitchen table, morning light", "provider": "local_diffusion"}).json()
        j = wait(c, s["jobs"][0]["id"])
        assert j["status"] == "succeeded", j.get("error")
        a_ = c.get(f"/assets/{j['result']['asset_ids'][0]}").json()
        assert a_["is_ai_generated"], "expected AI background"
        return f"{a_['provider']}/{a_['model']} · doc={a_['meta'].get('document_id')}"

    @step("Feature-callout infographic (template + brand fonts)")
    def infographic():
        s = c.post("/creative/generate", json={"creative_type": "feature", "product_id": pid}).json()
        j = wait(c, s["jobs"][0]["id"])
        assert j["status"] == "succeeded", j.get("error")
        return f"document {j['result']['document_id']}"

    @step("Object removal (LaMa ONNX, local)")
    def remove_obj():
        assets = c.get("/assets", params={"product_id": pid, "source": "upload", "kind": "image"}).json()["items"]
        src = assets[0]
        im = Image.new("L", (src["width"], src["height"]), 0)
        w, h = src["width"], src["height"]
        im.paste(255, (int(w * 0.05), int(h * 0.05), int(w * 0.2), int(h * 0.2)))
        buf = io.BytesIO()
        im.save(buf, "PNG")
        mask = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
        j = wait(c, c.post("/edits", json={"asset_id": src["id"], "operation": "remove_object", "mask": mask}).json()["id"])
        assert j["status"] == "succeeded", j.get("error")
        return f"{j['result']['provider']}/{j['result']['model']} ai={j['result']['ai']} {j['result'].get('note') or ''}"

    @step("Video render (FFmpeg)")
    def video():
        v = c.post("/videos", json={"name": "E2E reel", "product_id": pid, "aspect": "9:16", "target_duration": 8}).json()
        j = wait(c, c.post(f"/videos/{v['id']}/render").json()["id"])
        assert j["status"] == "succeeded", j.get("error")
        return f"{j['result']['duration_s']}s MP4"

    for fn in (listing, research, white, lifestyle, infographic, remove_obj, video):
        fn()
    print("\nSUMMARY")
    for name, ok, d in results:
        print(f"{'PASS' if ok else 'FAIL'} | {name} | {d}")
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
