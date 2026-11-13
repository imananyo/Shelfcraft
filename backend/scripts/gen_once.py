"""Dev helper: run one creative generation and save the output. Fails fast if the API is down.

Usage: python scripts/gen_once.py <product_id> <creative_type> <out.png> [--seed N] [--extra "..."] [--provider local_diffusion]
"""
from __future__ import annotations

import argparse
import sys
import time

import httpx

ap = argparse.ArgumentParser()
ap.add_argument("product_id")
ap.add_argument("creative_type")
ap.add_argument("out")
ap.add_argument("--seed", type=int)
ap.add_argument("--extra", default="")
ap.add_argument("--provider")
ap.add_argument("--size", type=int, default=1024)
ap.add_argument("--api", default="http://127.0.0.1:8000")
a = ap.parse_args()
c = httpx.Client(base_url=f"{a.api}/api", timeout=30)
for _ in range(20):
    try:
        c.get("/health").raise_for_status()
        break
    except httpx.HTTPError:
        time.sleep(1.5)
else:
    sys.exit("API not reachable")
r = c.post("/creative/generate", json={"creative_type": a.creative_type, "product_id": a.product_id, "width": a.size, "height": a.size,
                                         "extra_prompt": a.extra, "provider": a.provider, "seed": a.seed})
r.raise_for_status()
jid = r.json()["jobs"][0]["id"]
t0 = time.time()
while time.time() - t0 < 900:
    j = c.get(f"/jobs/{jid}").json()
    if j["status"] in ("succeeded", "failed", "cancelled"):
        break
    time.sleep(3)
if j["status"] != "succeeded":
    sys.exit(f"job {j['status']}: {j.get('error')}")
asset = c.get(f"/assets/{j['result']['asset_ids'][0]}").json()
open(a.out, "wb").write(c.get(asset["url"].removeprefix("/api")).content)
m = asset["meta_full"]
print(f"{time.time() - t0:.0f}s | {asset['provider']}/{asset['model']} | artifacts_removed={m.get('text_artifacts_removed')} | prompt: {m.get('prompt')}")
