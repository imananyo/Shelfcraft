"""Marketplace listing structure and length guidance.

These numbers are *guidance* drawn from commonly published seller documentation and are not
validated against live marketplace rules. The UI shows them as editable limits with a
"verify in Seller Central / admin" note; Shelfcraft never claims compliance.
"""
from __future__ import annotations

from typing import Any

MARKETPLACES: dict[str, dict[str, Any]] = {
    "amazon": {
        "label": "Amazon",
        "fields": {
            "title": {"max_chars": 200, "note": "Amazon's general title limit; many categories recommend ≤ 80–125 "
                      "characters and some newer policies are stricter. Verify for your category."},
            "bullets": {"count": 5, "max_chars": 255, "note": "Five key product features; keep each concise."},
            "description": {"max_chars": 2000},
            "search_terms": {"max_bytes": 249, "note": "Backend search terms; no brand names, ASINs or repeats."},
        },
        "image_slots": ["main_white", "lifestyle", "infographic_features", "infographic_benefits",
                        "comparison", "dimensions", "detail"],
        "image_size": [2000, 2000],
        "main_image_rules": "Pure white background (RGB 255,255,255), product fills ~85% of frame. Verify current rules.",
    },
    "amazon_mobile": {
        "label": "Amazon Mobile",
        "mobile": True,  # templates scale text up ~1.25× for small screens
        "fields": {
            "title": {"max_chars": 80, "note": "Mobile search shows roughly the first 70–80 characters — front-load brand, product and key benefit."},
            "bullets": {"count": 5, "max_chars": 200, "note": "Mobile shows the first bullets collapsed; lead with the strongest."},
            "description": {"max_chars": 2000},
            "search_terms": {"max_bytes": 249, "note": "Backend search terms; no brand names, ASINs or repeats."},
        },
        "image_slots": ["main_white", "infographic_features", "lifestyle", "infographic_benefits", "comparison", "dimensions", "detail"],
        "image_size": [1600, 1600],
        "main_image_rules": "Pure white background; product large in frame; any infographic text sized for phones.",
    },
    "shopify": {
        "label": "Shopify",
        "fields": {
            "title": {"max_chars": 255},
            "bullets": {"count": 5, "max_chars": 300},
            "description": {"max_chars": 5000},
            "search_terms": {"max_chars": 320, "note": "Used as SEO meta description guidance."},
        },
        "image_slots": ["main_white", "lifestyle", "infographic_features", "detail", "lifestyle_2", "comparison",
                        "dimensions"],
        "image_size": [2048, 2048],
    },
    "walmart": {
        "label": "Walmart",
        "fields": {
            "title": {"max_chars": 75, "note": "Walmart recommends 50–75 characters. Verify current guidance."},
            "bullets": {"count": 5, "max_chars": 200},
            "description": {"max_chars": 4000},
            "search_terms": {"max_chars": 250},
        },
        "image_slots": ["main_white", "lifestyle", "infographic_features", "detail", "comparison", "dimensions",
                        "lifestyle_2"],
        "image_size": [2000, 2000],
    },
    "tiktok": {
        "label": "TikTok Shop",
        "fields": {
            "title": {"max_chars": 255},
            "bullets": {"count": 5, "max_chars": 200},
            "description": {"max_chars": 10000},
            "search_terms": {"max_chars": 250},
        },
        "image_slots": ["main_white", "lifestyle", "infographic_features", "lifestyle_2", "detail", "comparison",
                        "dimensions"],
        "image_size": [1600, 1600],
    },
}

SIZE_PRESETS: list[dict[str, Any]] = [
    {"key": "amazon_main", "label": "Amazon main / listing image", "w": 2000, "h": 2000, "note": "Square; ≥1000 px enables zoom (verify)."},
    {"key": "square_1080", "label": "Square post", "w": 1080, "h": 1080},
    {"key": "portrait_4_5", "label": "Portrait 4:5 feed", "w": 1080, "h": 1350},
    {"key": "story_9_16", "label": "Story / Reel 9:16", "w": 1080, "h": 1920},
    {"key": "landscape_16_9", "label": "Landscape 16:9", "w": 1920, "h": 1080},
    {"key": "sb_image", "label": "Sponsored Brand image", "w": 1200, "h": 628, "note": "Size observed in reference app; verify in ad console."},
    {"key": "aplus_basic_banner", "label": "A+ Basic header banner", "w": 970, "h": 600, "note": "Common A+ module size; verify in A+ Content Manager."},
    {"key": "aplus_premium_banner", "label": "A+ Premium full-width", "w": 1464, "h": 600, "note": "Verify in A+ Content Manager."},
    {"key": "aplus_mobile", "label": "A+ Premium mobile", "w": 600, "h": 450, "note": "Verify in A+ Content Manager."},
    {"key": "shopify_product", "label": "Shopify product image", "w": 2048, "h": 2048},
]


def limits(marketplace: str) -> dict[str, Any]:
    return MARKETPLACES.get(marketplace, MARKETPLACES["amazon"])["fields"]


def validate_copy(marketplace: str, copy: dict[str, Any]) -> list[dict[str, Any]]:
    """Return guidance warnings (not compliance verdicts)."""
    lim = limits(marketplace)
    out: list[dict[str, Any]] = []
    title = copy.get("title") or ""
    if (m := lim["title"].get("max_chars")) and len(title) > m:
        out.append({"field": "title", "level": "warn", "message": f"Title is {len(title)} chars; guidance is ≤ {m}."})
    for i, b in enumerate(copy.get("bullets") or []):
        if (m := lim["bullets"].get("max_chars")) and len(b) > m:
            out.append({"field": f"bullets.{i}", "level": "warn", "message": f"Bullet {i + 1} is {len(b)} chars; guidance is ≤ {m}."})
    desc = copy.get("description") or ""
    if (m := lim["description"].get("max_chars")) and len(desc) > m:
        out.append({"field": "description", "level": "warn", "message": f"Description is {len(desc)} chars; guidance is ≤ {m}."})
    terms = copy.get("search_terms") or ""
    if (mb := lim["search_terms"].get("max_bytes")) and len(terms.encode()) > mb:
        out.append({"field": "search_terms", "level": "warn", "message": f"Search terms are {len(terms.encode())} bytes; guidance is ≤ {mb}."})
    elif (mc := lim["search_terms"].get("max_chars")) and len(terms) > mc:
        out.append({"field": "search_terms", "level": "warn", "message": f"Search terms are {len(terms)} chars; guidance is ≤ {mc}."})
    return out
