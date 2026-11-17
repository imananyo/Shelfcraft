"""Shelfcraft MCP server (stdio). Lets MCP clients (Claude Desktop, Claude Code, …) use your local workspace.

It calls the Shelfcraft public API (/v1) with an API key, so it has exactly the permissions of that key.

Run:     backend\\.venv\\Scripts\\python.exe backend\\mcp_server.py
Env:     SHELFCRAFT_API_KEY=sk_shelf_...   (Settings → API & MCP → Create key)
         SHELFCRAFT_API_URL=http://127.0.0.1:8000   (default)
"""
from __future__ import annotations

import os
import time
from typing import Any

import httpx
from mcp.server.mcpserver import MCPServer

API = os.environ.get("SHELFCRAFT_API_URL", "http://127.0.0.1:8000").rstrip("/") + "/v1"
KEY = os.environ.get("SHELFCRAFT_API_KEY", "")

server = MCPServer(
    name="shelfcraft",
    instructions=("Tools for a local e-commerce creative studio: browse products/brands, create listings (AI copy), "
                  "import products by ASIN / Walmart ID / URL, build listing image sets, A+ content, share links, translate and grade listings, and generate product images. Generation is asynchronous — use wait_for_job. "
                  "All AI runs on free or local models."),
)


def _client() -> httpx.Client:
    if not KEY:
        raise RuntimeError("SHELFCRAFT_API_KEY is not set. Create a key in Shelfcraft → Settings → API & MCP.")
    return httpx.Client(base_url=API, headers={"Authorization": f"Bearer {KEY}"}, timeout=60)


def _call(method: str, path: str, **kw: Any) -> Any:
    with _client() as c:
        r = c.request(method, path, **kw)
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail")
        except ValueError:
            detail = r.text[:300]
        raise RuntimeError(f"Shelfcraft API {r.status_code}: {detail}")
    return r.json()


@server.tool(description="List brands in the workspace (id, name, colors, tone).")
def list_brands() -> list[dict[str, Any]]:
    return [{k: b.get(k) for k in ("id", "name", "colors", "tagline", "tone_of_voice", "product_count")} for b in _call("GET", "/brands")]


@server.tool(description="Search products by name/SKU/category. Returns id, name, category, image_count.")
def list_products(query: str = "", limit: int = 50) -> list[dict[str, Any]]:
    data = _call("GET", "/products", params={"q": query or None, "limit": limit})
    return [{k: p.get(k) for k in ("id", "name", "category", "sku", "price", "image_count", "brand_name")} for p in data["items"]]


@server.tool(description="Get full product details (features, benefits, specs, images).")
def get_product(product_id: str) -> dict[str, Any]:
    return _call("GET", f"/products/{product_id}")


@server.tool(description="Create a product. Features/benefits are lists of short strings; only include real facts.")
def create_product(name: str, description: str = "", category: str = "", features: list[str] | None = None,
                   benefits: list[str] | None = None, price: float | None = None, brand_id: str | None = None) -> dict[str, Any]:
    return _call("POST", "/products", json={"name": name, "description": description or None, "category": category or None,
                                             "features": features or [], "benefits": benefits or [], "price": price, "brand_id": brand_id})


@server.tool(description="Create a marketplace listing for a product and start AI copy generation. "
                         "marketplace: amazon | amazon_mobile | shopify | walmart | tiktok. Returns the listing id and job.")
def create_listing(product_id: str, marketplace: str = "amazon", language: str = "en", country: str = "US") -> dict[str, Any]:
    out = _call("POST", "/listings", json={"product_id": product_id, "marketplace": marketplace, "language": language, "country": country})
    return {"listing_id": out["id"], "jobs": [{"id": j["id"], "status": j["status"]} for j in out.get("jobs", [])]}


@server.tool(description="Get a listing's current copy (title, bullets, description, search terms), length warnings and images.")
def get_listing(listing_id: str) -> dict[str, Any]:
    out = _call("GET", f"/listings/{listing_id}")
    return {k: out.get(k) for k in ("id", "name", "marketplace", "copy", "warnings", "provenance", "images", "jobs")}


@server.tool(description="Translate a listing into another language (creates a new listing). language: de, fr, es, it, ja, hi, …")
def translate_listing(listing_id: str, language: str, country: str = "US") -> dict[str, Any]:
    return _call("POST", f"/listings/{listing_id}/translate", params={"language": language, "country": country})


@server.tool(description="Grade a listing (0–100 with section scores and top fixes). Pass listing_id, or title/bullets/description.")
def grade_listing(listing_id: str | None = None, title: str = "", bullets: list[str] | None = None, description: str = "",
                  search_terms: str = "", marketplace: str = "amazon") -> dict[str, Any]:
    out = _call("POST", "/grader", json={"listing_id": listing_id, "title": title, "bullets": bullets or [], "description": description,
                                          "search_terms": search_terms, "marketplace": marketplace})
    return {"score": out["score"], "grade": out["grade"], "sections": {s["key"]: s["score"] for s in out["sections"]},
            "top_fixes": [f"[{f['section']}] {f['label']}: {f['fix']}" for f in out["top_fixes"]]}


@server.tool(description="Generate product creatives. creative_type: white_bg_main, hero, lifestyle, studio, detail, feature, "
                         "infographic, comparison, dimensions, steps, social, promo, lifestyle_headline, ad_sb.")
def generate_creative(creative_type: str, product_id: str | None = None, width: int = 1024, height: int = 1024,
                      style: str = "minimal", direction: str = "", count: int = 1) -> dict[str, Any]:
    out = _call("POST", "/creatives", json={"creative_type": creative_type, "product_id": product_id, "width": width, "height": height,
                                             "style": style, "extra_prompt": direction, "count": count})
    return {"session_id": out["session_id"], "job_ids": [j["id"] for j in out["jobs"]]}


@server.tool(description="Get a background job's status and result.")
def get_job(job_id: str) -> dict[str, Any]:
    j = _call("GET", f"/jobs/{job_id}")
    return {k: j.get(k) for k in ("id", "label", "status", "progress", "message", "error", "result")}


@server.tool(description="Wait (up to timeout_s) for a job to finish; returns the final job. Image jobs take ~30–60 s on CPU, copy ~2 min.")
def wait_for_job(job_id: str, timeout_s: int = 300) -> dict[str, Any]:
    t0 = time.time()
    while True:
        j = get_job(job_id)
        if j["status"] in ("succeeded", "failed", "cancelled") or time.time() - t0 > min(timeout_s, 900):
            return j
        time.sleep(3)


@server.tool(description="Get an asset's metadata (what model made it) and its download URL.")
def get_asset(asset_id: str) -> dict[str, Any]:
    a = _call("GET", f"/assets/{asset_id}")
    return {k: a.get(k) for k in ("id", "title", "kind", "width", "height", "provider", "model", "is_ai_generated", "download_url")}


@server.tool(description="Import a product from an Amazon ASIN, a Walmart item ID or any product URL (title, bullets, images, reviews).")
def import_product(value: str, kind: str = "asin", country: str = "US") -> dict[str, Any]:
    p = _call("POST", "/products/import", json={"kind": kind, "value": value, "country": country})
    return {"product_id": p["id"], "name": p["name"], "import": p.get("import"), "images_imported": p.get("images_imported")}


@server.tool(description="Generate a listing's full image set (main, lifestyle, infographics…). Returns a job id.")
def create_listing_visuals(listing_id: str, style: str = "minimal") -> dict[str, Any]:
    j = _call("POST", f"/listings/{listing_id}/images", params={"style": style})
    return {"job_id": j["id"]}


@server.tool(description="Add more visuals to an existing listing session, steered by a prompt (keep prompting).")
def add_visuals(listing_id: str, prompt: str = "", creative_type: str = "lifestyle", count: int = 2) -> dict[str, Any]:
    jobs = _call("POST", f"/listings/{listing_id}/images/more", json={"prompt": prompt, "creative_type": creative_type, "count": count})
    return {"job_ids": [j["id"] for j in jobs]}


@server.tool(description="Download every visual of a listing as a ZIP into your Downloads folder; returns the file path.")
def download_listing_visuals(listing_id: str) -> dict[str, Any]:
    from pathlib import Path

    with _client() as c:
        r = c.get(f"/listings/{listing_id}/visuals.zip")
    if r.status_code >= 400:
        raise RuntimeError(f"Shelfcraft API error {r.status_code}: {r.text[:200]}")
    out = Path.home() / "Downloads" / f"shelfcraft-listing-{listing_id}.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(r.content)
    return {"path": str(out), "bytes": len(r.content)}


@server.tool(description="List recent work (creative sessions).")
def list_recent_work(limit: int = 20) -> list[dict[str, Any]]:
    return _call("GET", "/recent-work", params={"limit": limit})


@server.tool(description="Rename a listing, A+ layout or design project.")
def rename_recent_work(project_id: str, name: str) -> dict[str, Any]:
    p = _call("PATCH", f"/projects/{project_id}", json={"name": name})
    return {"id": p.get("id"), "name": p.get("name")}


@server.tool(description="Create a no-login, view-only share link for a listing / A+ / design project.")
def share_link(project_id: str) -> dict[str, Any]:
    s = _call("POST", f"/projects/{project_id}/share")
    base = API.removesuffix("/v1").replace(":8000", ":3000")
    return {"url": base + s["url"] if s.get("url") else None}


@server.tool(description="Create an A+ content layout for a product (tier: basic | premium | mobile).")
def create_aplus(name: str, product_id: str | None = None, tier: str = "premium", modules: list[str] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"name": name, "product_id": product_id, "tier": tier}
    if modules:
        body["modules"] = modules
    a = _call("POST", "/aplus", json=body)
    return {"aplus_id": a["id"], "modules": [m["type"] for m in a.get("modules", [])]}


@server.tool(description="Make the mobile version of a desktop A+ layout, keeping edited text and images.")
def convert_a_plus_desktop_to_mobile(aplus_id: str) -> dict[str, Any]:
    a = _call("POST", f"/aplus/{aplus_id}/convert-mobile")
    return {"aplus_id": a["id"], "tier": a.get("tier"), "modules": len(a.get("modules", []))}


@server.tool(description="AI usage by provider over the last N days.")
def get_usage(days: int = 30) -> dict[str, Any]:
    return _call("GET", "/usage", params={"days": days})


if __name__ == "__main__":
    server.run("stdio")
