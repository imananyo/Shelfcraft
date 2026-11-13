"""Dev helper: run product research with sample reviews and print the sentiment section."""
import json
import sys
import time

import httpx

c = httpx.Client(base_url="http://127.0.0.1:8000/api", timeout=30)
for _ in range(30):
    try:
        c.get("/health").raise_for_status()
        break
    except httpx.HTTPError:
        time.sleep(1.5)
pid = sys.argv[1]
reviews = ("Love the speckled glaze, looks handmade. The handle is comfy. Keeps coffee warm a while. "
           "Wish it were a bit bigger. One arrived with a small chip.")
j = c.post(f"/products/{pid}/research", json={"reviews": reviews}).json()
while (s := c.get(f"/jobs/{j['id']}").json())["status"] not in ("succeeded", "failed"):
    time.sleep(3)
print(s["status"], s.get("error"))
r = c.get(f"/products/{pid}/research").json()[0]
print(r["provider"], r["model"])
print(json.dumps(r["result"].get("review_sentiment"), indent=1))
print("assumptions:", r["result"].get("assumptions"))
