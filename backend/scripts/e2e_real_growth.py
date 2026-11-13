"""Real-model smoke run for the growth features (translate, packaging, ads, voiceover video). Needs the app running."""
from __future__ import annotations

import os
import sys
import time

import httpx

c = httpx.Client(base_url=os.environ.get("SHELFCRAFT_API", "http://127.0.0.1:8000") + "/api", timeout=60)
results: list[tuple[str, bool, str]] = []


def wait(job_id: str, limit: float = 1500) -> dict:
    t0 = time.time()
    while time.time() - t0 < limit:
        j = c.get(f"/jobs/{job_id}").json()
        if j["status"] in ("succeeded", "failed", "cancelled"):
            return j
        time.sleep(4)
    raise TimeoutError(job_id)


def step(name, fn):
    t0 = time.time()
    try:
        d = fn()
        results.append((name, True, f"{time.time() - t0:.0f}s · {d}"))
    except Exception as e:  # noqa: BLE001
        results.append((name, False, f"{time.time() - t0:.0f}s · {type(e).__name__}: {e}"))
    print(("PASS " if results[-1][1] else "FAIL ") + name + " — " + results[-1][2], flush=True)


pid = next(p["id"] for p in c.get("/products").json()["items"] if "Mug" in p["name"])
listing = next((x for x in c.get("/listings").json() if x["has_copy"]), None)


def translate():
    j = wait(c.post(f"/listings/{listing['id']}/translate", json={"language": "de", "country": "DE", "translate_images": False}).json()["id"])
    assert j["status"] == "succeeded", j.get("error")
    t = c.get(f"/listings/{j['result']['project_id']}").json()["copy"]
    return f"{j['result']['provider']}/{j['result']['model']} · DE title: {t['title'][:70]!r}"


def packaging():
    j = wait(c.post("/labs/packaging", json={"product_id": pid, "count": 5}).json()["id"])
    assert j["status"] == "succeeded", j.get("error")
    d = c.get(f"/labs/packaging/{j['result']['project_id']}").json()
    return f"{len(d['concepts'])} concepts · first: {d['concepts'][0].get('name')!r}"


def ads():
    a = c.post("/ads", json={"product_id": pid, "format": "sb_image", "count": 4}).json()
    j = wait(a["job"]["id"])
    assert j["status"] == "succeeded", j.get("error")
    d = c.get(f"/ads/{a['id']}").json()
    return f"{len(d['concepts'])} concepts · e.g. {d['concepts'][0].get('headline')!r}"


def voiceover():
    v = c.post("/videos", json={"name": "VO real", "product_id": pid, "aspect": "9:16", "target_duration": 8}).json()
    j = wait(c.post(f"/videos/{v['id']}/voiceover", json={}).json()["id"])
    assert j["status"] == "succeeded", j.get("error")
    return f"{j['result']['lines']} spoken lines · {j['result']['duration_s']}s MP4"


if listing:
    step("Translate listing to German (Ollama)", translate)
step("Packaging ideas (Ollama)", packaging)
step("Ad concepts (Ollama)", ads)
step("Voiceover video (Ollama script + offline Windows voice + FFmpeg)", voiceover)
print("\nSUMMARY")
for n, ok, d in results:
    print(f"{'PASS' if ok else 'FAIL'} | {n} | {d}")
sys.exit(0 if all(ok for _, ok, _ in results) else 1)
