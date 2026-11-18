"""Playbooks (reusable generation recipes) and re-using a finished design for a different product."""
from __future__ import annotations

import copy
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Asset, Brand, EditorDocument, FactoryBatch, Playbook, Product
from app.jobs import queue
from app.services.creative import CREATIVE_TYPES, get_or_make_cutout, main_product_asset
from app.services.documents import create_document, document_json
from app.services.templates import _PH, default_values

STEP_KINDS = {"creative", "listing_copy", "research", "video", "aplus", "packaging"}
STYLES = {"minimal", "luxury", "natural", "vibrant", "editorial", "tech"}
ASPECTS = {"16:9", "9:16", "1:1", "4:5"}
APLUS_TIERS = {"premium", "basic", "mobile"}
DEFAULT_APLUS_MODULES = ["hero_banner", "feature_row", "comparison"]
# Rough CPU-only minutes per step on a 4-core laptop (shown as an estimate before a run).
STEP_MINUTES = {"creative": 1.0, "listing_copy": 2.5, "research": 3.0, "video": 1.5, "aplus": 0.5, "packaging": 2.5}
# Which keys each step kind keeps (anything else is dropped so stale fields never leak between kinds).
_STEP_KEYS = {
    "creative": {"creative_type", "style", "extra_prompt", "width", "height"},
    "listing_copy": {"marketplace", "language", "country"},
    "research": set(),
    "video": {"aspect", "duration", "voiceover"},
    "aplus": {"tier", "modules"},
    "packaging": {"count"},
}
_SETTING_KEYS = {"style", "marketplace", "width", "height"}

# Original Shelfcraft recipes (structure inspired by common seller workflows).
LIBRARY: list[dict[str, Any]] = [
    {"name": "Marketplace main image set", "category": "listing", "description":
     "White-background main, premium hero, feature callouts, benefit headline, comparison and size graphic.",
     "settings": {"style": "minimal"}, "steps": [
         {"kind": "creative", "creative_type": "white_bg_main"}, {"kind": "creative", "creative_type": "hero"},
         {"kind": "creative", "creative_type": "feature"}, {"kind": "creative", "creative_type": "lifestyle_headline"},
         {"kind": "creative", "creative_type": "comparison"}, {"kind": "creative", "creative_type": "dimensions"}]},
    {"name": "Lifestyle trio", "category": "lifestyle", "description": "Three lifestyle scenes in different moods.",
     "settings": {}, "steps": [
         {"kind": "creative", "creative_type": "lifestyle", "style": "natural", "extra_prompt": "morning light, calm home"},
         {"kind": "creative", "creative_type": "lifestyle", "style": "editorial", "extra_prompt": "evening, warm lamps"},
         {"kind": "creative", "creative_type": "lifestyle", "style": "vibrant", "extra_prompt": "bright, playful colors"}]},
    {"name": "Social & UGC-style kit", "category": "social", "description":
     "Vertical voiceover video, a 4:5 social post and a story-format slideshow — creator-style content without an avatar.",
     "settings": {"style": "vibrant"}, "steps": [
         {"kind": "video", "aspect": "9:16", "duration": 15, "voiceover": True}, {"kind": "creative", "creative_type": "social"},
         {"kind": "creative", "creative_type": "lifestyle", "extra_prompt": "casual everyday moment"}]},
    {"name": "Furniture & home lifestyle", "category": "lifestyle", "description": "Room-scale scenes for furniture and décor.",
     "settings": {"style": "natural"}, "steps": [
         {"kind": "creative", "creative_type": "studio", "extra_prompt": "bright living room corner, wooden floor"},
         {"kind": "creative", "creative_type": "lifestyle", "extra_prompt": "scandinavian living room, soft daylight"},
         {"kind": "creative", "creative_type": "dimensions"}]},
    {"name": "Full launch kit", "category": "launch", "description":
     "Research, listing copy, image set, A+ content and a listing video — everything for a new product.",
     "settings": {"marketplace": "amazon", "style": "minimal"}, "steps": [
         {"kind": "research"}, {"kind": "listing_copy", "marketplace": "amazon"},
         {"kind": "creative", "creative_type": "white_bg_main"}, {"kind": "creative", "creative_type": "lifestyle"},
         {"kind": "creative", "creative_type": "feature"}, {"kind": "aplus", "tier": "premium"},
         {"kind": "video", "aspect": "16:9", "duration": 15}]},
    {"name": "Multi-marketplace copy", "category": "listing", "description":
     "Research once, then listing copy for Amazon, Walmart and Shopify — each within that marketplace's limits.",
     "settings": {}, "steps": [
         {"kind": "research"}, {"kind": "listing_copy", "marketplace": "amazon"},
         {"kind": "listing_copy", "marketplace": "walmart"}, {"kind": "listing_copy", "marketplace": "shopify"}]},
    {"name": "EU expansion copy", "category": "launch", "description":
     "Amazon listing copy written natively in German, French, Spanish and Italian (not word-for-word translations).",
     "settings": {"marketplace": "amazon"}, "steps": [
         {"kind": "listing_copy", "language": "de", "country": "DE"}, {"kind": "listing_copy", "language": "fr", "country": "FR"},
         {"kind": "listing_copy", "language": "es", "country": "ES"}, {"kind": "listing_copy", "language": "it", "country": "IT"}]},
    {"name": "A+ & brand story", "category": "listing", "description":
     "Premium A+ layout with brand story and comparison, plus matching lifestyle and detail images.",
     "settings": {"style": "editorial"}, "steps": [
         {"kind": "aplus", "tier": "premium", "modules": ["hero_banner", "brand_story", "feature_row", "comparison"]},
         {"kind": "creative", "creative_type": "lifestyle"}, {"kind": "creative", "creative_type": "detail"}]},
]


def seed_library(db: Session) -> None:
    have = {p.name for p in db.scalars(select(Playbook).where(Playbook.is_template.is_(True)))}
    for t in LIBRARY:
        if t["name"] not in have:
            db.add(Playbook(name=t["name"], description=t["description"], category=t["category"], steps=t["steps"],
                            settings=t["settings"], is_template=True))


def _int(v: Any, lo: int, hi: int, what: str) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise ValueError(f"{what} must be a number") from None
    if not lo <= n <= hi:
        raise ValueError(f"{what} must be between {lo} and {hi}")
    return n


def _size(out: dict[str, Any], src: dict[str, Any], where: str) -> None:
    for k in ("width", "height"):
        if src.get(k) not in (None, ""):
            out[k] = _int(src[k], 256, 4096, f"{where} {k}")


def validate_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Check every step and return cleaned copies (unknown keys dropped, values range-checked)."""
    from app.services.growth import LANGUAGES
    from app.services.marketplaces import MARKETPLACES

    if not steps:
        raise ValueError("a playbook needs at least one step")
    if len(steps) > 20:
        raise ValueError("at most 20 steps")
    out: list[dict[str, Any]] = []
    for n, s in enumerate(steps, 1):
        kind = s.get("kind")
        if kind not in STEP_KINDS:
            raise ValueError(f"step {n}: unknown step kind {kind}")
        c: dict[str, Any] = {"kind": kind}
        c.update({k: v for k, v in s.items() if k in _STEP_KEYS[kind] and v not in (None, "")})
        if kind == "creative":
            if c.get("creative_type") not in CREATIVE_TYPES:
                raise ValueError(f"step {n}: choose an image type")
            if c.get("style") and c["style"] not in STYLES:
                raise ValueError(f"step {n}: unknown style {c['style']}")
            if "extra_prompt" in c:
                c["extra_prompt"] = str(c["extra_prompt"]).strip()[:500] or None
            _size(c, s, f"step {n}")
        elif kind == "listing_copy":
            if c.get("marketplace") and c["marketplace"] not in MARKETPLACES:
                raise ValueError(f"step {n}: unknown marketplace {c['marketplace']}")
            if c.get("language") and c["language"] not in LANGUAGES:
                raise ValueError(f"step {n}: unsupported language {c['language']}")
            if "country" in c:
                c["country"] = str(c["country"]).strip().upper()[:2] or None
        elif kind == "video":
            if c.get("aspect") and c["aspect"] not in ASPECTS:
                raise ValueError(f"step {n}: unknown aspect ratio {c['aspect']}")
            if "duration" in c:
                c["duration"] = _int(c["duration"], 5, 60, f"step {n} video length")
            c["voiceover"] = bool(c.get("voiceover"))
        elif kind == "aplus":
            from app.routers.aplus import MODULE_TYPES

            if c.get("tier") and c["tier"] not in APLUS_TIERS:
                raise ValueError(f"step {n}: unknown A+ tier {c['tier']}")
            mods = c.get("modules")
            if mods is not None:
                if not isinstance(mods, list) or not mods or len(mods) > 7 or any(m not in MODULE_TYPES for m in mods):
                    raise ValueError(f"step {n}: choose 1–7 valid A+ modules")
        elif kind == "packaging" and "count" in c:
            c["count"] = _int(c["count"], 1, 20, f"step {n} idea count")
        out.append({k: v for k, v in c.items() if v is not None})
    return out


def validate_settings(settings: dict[str, Any]) -> dict[str, Any]:
    """Playbook-wide defaults that a step can override (style, marketplace, image size)."""
    from app.services.marketplaces import MARKETPLACES

    c: dict[str, Any] = {k: v for k, v in (settings or {}).items() if k in _SETTING_KEYS and v not in (None, "")}
    if c.get("style") and c["style"] not in STYLES:
        raise ValueError(f"unknown default style {c['style']}")
    if c.get("marketplace") and c["marketplace"] not in MARKETPLACES:
        raise ValueError(f"unknown default marketplace {c['marketplace']}")
    _size(c, settings or {}, "default image")
    return c


def estimate_minutes(steps: list[dict[str, Any]], products: int = 1) -> float:
    per = sum(STEP_MINUTES.get(s.get("kind", ""), 1.0) + (1.0 if s.get("voiceover") else 0.0) for s in steps)
    return round(per * max(products, 1), 1)


def run_playbook(db: Session, playbook: Playbook, product_ids: list[str], *, brand_id: str | None, max_jobs: int) -> FactoryBatch:
    steps = validate_steps(list(playbook.steps or []))
    product_ids = list(dict.fromkeys(product_ids))  # a product picked twice runs once
    total = len(steps) * len(product_ids)
    if total > max_jobs:
        raise ValueError(f"{total} steps exceeds the per-run limit of {max_jobs}")
    b = FactoryBatch(name=f"Playbook: {playbook.name}", total=total,
                     config={"playbook_id": playbook.id, "brand_id": brand_id, **(playbook.settings or {})})
    db.add(b)
    db.flush()
    for pid in product_ids:
        p = db.get(Product, pid)
        if p is None:
            raise ValueError("product not found")
        for i, step in enumerate(steps):
            # Steps for one product keep their order (priority decreases), products interleave fairly.
            queue.enqueue(db, "playbook_step", {"batch_id": b.id, "product_id": pid, "product_name": p.name, "step": step,
                                                "step_index": i, "creative_type": step.get("creative_type") or step["kind"]},
                          batch_id=b.id, priority=-1 - i)
    return b


# ---------------------------------------------------------------- reuse a design for another product
def apply_document_to_product(db: Session, doc_id: str, product_id: str, *, project_id: str | None = None) -> EditorDocument:
    src = db.get(EditorDocument, doc_id)
    target = db.get(Product, product_id)
    if src is None or target is None:
        raise ValueError("design or product not found")
    doc = copy.deepcopy(document_json(src))
    brand = db.get(Brand, target.brand_id) if target.brand_id else None
    values = default_values(target, brand, None)
    # Source product (if known) for literal text substitution on designs not made from templates.
    src_product = None
    for layer in doc["layers"]:
        if layer.get("type") == "image" and layer.get("assetId"):
            a = db.get(Asset, layer["assetId"])
            if a and a.product_id and a.product_id != target.id:
                src_product = db.get(Product, a.product_id)
                break
    tgt_src = main_product_asset(db, target)
    cutout = get_or_make_cutout(db, target, tgt_src) if tgt_src else None
    tgt_images = [pi.asset_id for pi in target.images if pi.role != "cutout"]
    swaps: dict[str, str | None] = {}
    if src_product:
        swaps[src_product.name] = target.name
        for a, b in zip(src_product.features or [], target.features or []):
            swaps[a] = b
        for a, b in zip(src_product.benefits or [], target.benefits or []):
            swaps[a] = b
    img_queue = list(tgt_images)
    for layer in doc["layers"]:
        if layer.get("type") == "text":
            if layer.get("template_text"):
                layer["text"] = _PH.sub(lambda m: values.get(m.group(1), ""), layer["template_text"])
            else:
                for old, new in swaps.items():
                    if old and new and old in (layer.get("text") or ""):
                        layer["text"] = layer["text"].replace(old, new)
        elif layer.get("type") == "image":
            ph = layer.get("placeholder")
            a = db.get(Asset, layer["assetId"]) if layer.get("assetId") else None
            is_product_asset = bool(a and a.product_id and a.product_id != target.id and ph != "background")
            if ph == "product_cutout" or (is_product_asset and (a.meta or {}).get("operation") == "remove_background"):
                layer["assetId"] = cutout.id if cutout else layer.get("assetId")
            elif ph == "product_image" or is_product_asset:
                layer["assetId"] = (img_queue.pop(0) if img_queue else (cutout.id if cutout else layer.get("assetId")))
    return create_document(db, name=f"{src.name.split(' — ')[0]} — {target.name}"[:200], doc=doc, project_id=project_id or src.project_id)
