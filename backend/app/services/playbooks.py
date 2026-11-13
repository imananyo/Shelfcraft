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
]


def seed_library(db: Session) -> None:
    have = {p.name for p in db.scalars(select(Playbook).where(Playbook.is_template.is_(True)))}
    for t in LIBRARY:
        if t["name"] not in have:
            db.add(Playbook(name=t["name"], description=t["description"], category=t["category"], steps=t["steps"],
                            settings=t["settings"], is_template=True))


def validate_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not steps:
        raise ValueError("a playbook needs at least one step")
    if len(steps) > 20:
        raise ValueError("at most 20 steps")
    for s in steps:
        if s.get("kind") not in STEP_KINDS:
            raise ValueError(f"unknown step kind {s.get('kind')}")
        if s["kind"] == "creative" and s.get("creative_type") not in CREATIVE_TYPES:
            raise ValueError(f"unknown creative type {s.get('creative_type')}")
    return steps


def run_playbook(db: Session, playbook: Playbook, product_ids: list[str], *, brand_id: str | None, max_jobs: int) -> FactoryBatch:
    steps = validate_steps(list(playbook.steps or []))
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
