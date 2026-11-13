"""Translate listings, packaging concepts, and Amazon Ads concept brainstorming."""
from __future__ import annotations

import copy
from typing import Any

from sqlalchemy.orm import Session

from app.ai import fallback_manager as fm
from app.ai.base import TextRequest
from app.db.models import Brand, EditorDocument, Product, ProductResearch, Project
from app.routers.brands import brand_context
from app.services.copywriting import SYSTEM, product_facts
from app.services.documents import create_document, document_json
from app.services.marketplaces import validate_copy

LANGUAGES = {"en": "English", "de": "German", "fr": "French", "es": "Spanish", "it": "Italian", "pt": "Portuguese",
             "nl": "Dutch", "pl": "Polish", "sv": "Swedish", "tr": "Turkish", "ar": "Arabic", "hi": "Hindi", "ja": "Japanese",
             "zh": "Chinese (Simplified)"}


# ---------------------------------------------------------------- translate
def translate_texts(texts: list[str], language: str, *, context: str = "", provider: str | None = None) -> tuple[list[str], str, str]:
    """Translate a list of short strings, preserving order/count. Falls back to originals for blanks."""
    lang = LANGUAGES.get(language, language)
    items = [t for t in texts]
    prompt = (f"Translate each item into {lang} for an e-commerce listing{(' (' + context + ')') if context else ''}. "
              "Localize naturally for shoppers (units, idioms) but keep brand and product names unchanged. "
              "Keep any leading CAPITALIZED benefit header followed by a colon. Return JSON {\"items\": [...]} with "
              f"exactly {len(items)} strings in the same order.\n\n" + "\n".join(f"{i + 1}. {t}" for i, t in enumerate(items)))
    res = fm.generate_text(TextRequest(prompt=prompt, system="You are a professional e-commerce localizer. Respond with JSON only.",
                                       json_mode=True, temperature=0.2, max_tokens=3000), purpose="translate", preferred=provider)
    out = res.json().get("items") if isinstance(res.json(), dict) else None
    if not isinstance(out, list) or len(out) != len(items):
        raise ValueError("translation returned a different number of items — try again or use a larger model")
    return [str(o) if str(o).strip() else items[i] for i, o in enumerate(out)], res.provider, res.model


def translate_listing(db: Session, project_id: str, language: str, country: str, *, translate_images: bool = True,
                      provider: str | None = None, progress: Any = None) -> dict[str, Any]:
    tick = progress or (lambda *_a, **_k: None)
    src = db.get(Project, project_id)
    if src is None or src.kind != "listing":
        raise ValueError("listing not found")
    data = src.data or {}
    from app.services.copywriting import normalize_copy

    c = normalize_copy(data.get("copy")) or {}
    if not c:
        raise ValueError("this listing has no copy yet — generate it first")
    fields = [c.get("title", ""), *(c.get("bullets") or []), c.get("description", ""), c.get("search_terms", ""),
              c.get("headline", ""), c.get("subheadline", ""), ", ".join(c.get("keywords") or [])]
    tick(0.15, "Translating copy")
    tr, prov, model = translate_texts(fields, language, context=f"{data.get('marketplace', 'amazon')} {country}", provider=provider)
    nb = len(c.get("bullets") or [])
    new_copy = {**c, "title": tr[0], "bullets": tr[1:1 + nb], "description": tr[1 + nb], "search_terms": tr[2 + nb],
                "headline": tr[3 + nb], "subheadline": tr[4 + nb],
                "keywords": [k.strip() for k in tr[5 + nb].split(",") if k.strip()]}
    lang_name = LANGUAGES.get(language, language)
    p = Project(kind="listing", name=f"{src.name} — {lang_name} ({country})"[:200], product_id=src.product_id, brand_id=src.brand_id,
                data={"marketplace": data.get("marketplace", "amazon"),
                      "options": {**data.get("options", {}), "language": language, "country": country},
                      "copy": new_copy, "warnings": validate_copy(data.get("marketplace", "amazon"), new_copy),
                      "provenance": {"provider": prov, "model": model, "translated_from": src.id}, "images": []})
    db.add(p)
    db.flush()
    images_out: list[dict[str, Any]] = []
    if translate_images:
        from app.imaging.render import render_png
        from app.services.assets import create_asset_from_bytes

        items = data.get("images") or []
        for i, item in enumerate(items):
            doc_id = item.get("document_id")
            d = db.get(EditorDocument, doc_id) if doc_id else None
            if d is None:
                images_out.append(item)  # flat image (e.g. white main): reuse as-is — no text to translate
                continue
            tick(0.3 + 0.6 * i / max(1, len(items)), f"Translating image {i + 1}/{len(items)}")
            doc = copy.deepcopy(document_json(d))
            text_layers = [layer for layer in doc["layers"] if layer["type"] == "text" and (layer.get("text") or "").strip()]
            if text_layers:
                translated, _, _ = translate_texts([layer["text"] for layer in text_layers], language, provider=provider)
                for layer, t in zip(text_layers, translated):
                    layer["text"] = t
            for layer in doc["layers"]:
                layer["id"] = layer["id"][:24] + "t"
            nd = create_document(db, name=f"{d.name} ({lang_name})", doc=doc, project_id=p.id)
            a = create_asset_from_bytes(db, render_png(doc), ext="png", source="generated", filename=f"{nd.name}.png", title=nd.name,
                                        product_id=src.product_id, project_id=p.id, provider=prov, model=f"{model} (translation)",
                                        is_ai_generated=True, meta={"document_id": nd.id, "operation": "translate", "language": language})
            nd.thumbnail_asset_id = a.id
            images_out.append({"slot": item.get("slot"), "asset_ids": [a.id], "document_id": nd.id})
        p.data = {**p.data, "images": images_out}
    return {"project_id": p.id, "provider": prov, "model": model, "images": len(images_out)}


# ---------------------------------------------------------------- packaging ideas
def packaging_ideas(db: Session, product_id: str, *, count: int = 15, notes: str = "", provider: str | None = None) -> dict[str, Any]:
    p = db.get(Product, product_id)
    if p is None:
        raise ValueError("product not found")
    count = max(3, min(15, count))
    prompt = (f"Propose {count} distinct packaging concepts for this product. Vary structure, materials, sustainability and "
              f"shelf impact. Ground every concept in the product facts.\n\n{product_facts(p)}\n\n"
              f"{brand_context(db, p.brand_id)}\nNotes from the user: {notes or '(none)'}\n\n"
              'Return JSON {"concepts": [{"name": "...", "big_idea": "...", "structure": "box|pouch|tube|tin|sleeve|...", '
              '"materials": "...", "palette": ["#hex", "#hex", "#hex"], "typography": "...", "front_panel_copy": "...", '
              '"unboxing": "...", "sustainability": "...", "best_for": "...", "cost_level": "low|medium|high"}], '
              '"assumptions": ["..."]}')
    res = fm.generate_text(TextRequest(prompt=prompt, system=SYSTEM, json_mode=True, temperature=0.8, max_tokens=3500),
                           purpose="packaging_ideas", preferred=provider)
    data = res.json()
    if not isinstance(data, dict) or not isinstance(data.get("concepts"), list):
        raise ValueError("model returned unexpected JSON")
    return {"concepts": data["concepts"][:count], "assumptions": data.get("assumptions", []), "provider": res.provider, "model": res.model}


# ---------------------------------------------------------------- amazon ads concepts
AD_FORMATS = {
    "sb_image": {"label": "Sponsored Brand image", "w": 1200, "h": 628, "kind": "image"},
    "sb_video": {"label": "Sponsored Brand video", "w": 1920, "h": 1080, "kind": "video", "aspect": "16:9", "duration": 10},
    "sp_video": {"label": "Sponsored Products video", "w": 1920, "h": 1080, "kind": "video", "aspect": "16:9", "duration": 10},
    "social_feed": {"label": "Social feed ad 4:5", "w": 1080, "h": 1350, "kind": "image"},
    "story_ad": {"label": "Story / Reels ad 9:16", "w": 1080, "h": 1920, "kind": "video", "aspect": "9:16", "duration": 10},
}


def ad_concepts(db: Session, product_id: str, *, count: int = 6, personas: list[str] | None = None, goal: str = "conversions",
                provider: str | None = None) -> dict[str, Any]:
    p = db.get(Product, product_id)
    if p is None:
        raise ValueError("product not found")
    research = db.query(ProductResearch).filter(ProductResearch.product_id == p.id).order_by(ProductResearch.created_at.desc()).first()
    known = [x.get("name") for x in ((research.result or {}).get("personas") or [])] if research else []
    personas = [x for x in (personas or known) if x][:4] or ["General shopper"]
    prompt = (f"Brainstorm {count} ad concepts for A/B testing (goal: {goal}). Spread them across these personas: "
              f"{', '.join(personas)}. Each concept must test a different angle (benefit, pain point, social proof from supplied "
              "data only, comparison, lifestyle, value). Headlines ≤ 50 characters, no unverifiable claims.\n\n"
              f"{product_facts(p)}\n\n{brand_context(db, p.brand_id)}\n\n"
              'Return JSON {"concepts": [{"persona": "...", "angle": "...", "headline": "...", "subheadline": "...", "cta": "...", '
              '"visual": "short scene description", "hypothesis": "what this variant tests"}]}')
    res = fm.generate_text(TextRequest(prompt=prompt, system=SYSTEM, json_mode=True, temperature=0.85, max_tokens=2500),
                           purpose="ad_concepts", preferred=provider)
    data = res.json()
    if not isinstance(data, dict) or not isinstance(data.get("concepts"), list):
        raise ValueError("model returned unexpected JSON")
    return {"concepts": data["concepts"][:count], "personas": personas, "provider": res.provider, "model": res.model}


def brand_of(db: Session, product: Product | None) -> Brand | None:
    return db.get(Brand, product.brand_id) if product and product.brand_id else None
