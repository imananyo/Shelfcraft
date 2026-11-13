"""LLM-backed product intelligence and listing copy. Prompts force grounding in supplied data
and require the model to list its assumptions separately."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.ai import fallback_manager as fm
from app.ai.base import TextRequest
from app.db.models import Brand, Product, ProductResearch
from app.routers.brands import brand_context
from app.services.marketplaces import MARKETPLACES, limits

SYSTEM = (
    "You are a senior e-commerce strategist and copywriter. Use ONLY the facts provided. "
    "Never invent certifications, awards, clinical results, rankings, or specifications. "
    "When you infer something not stated, put it in the `assumptions` list. Respond with JSON only."
)


def product_facts(p: Product) -> str:
    lines = [f"Product name: {p.name}"]
    for label, val in (("Category", p.category), ("SKU", p.sku), ("Price", f"{p.price} {p.currency}" if p.price else None),
                       ("Description", p.description)):
        if val:
            lines.append(f"{label}: {val}")
    if p.features:
        lines.append("Features:\n" + "\n".join(f"- {f}" for f in p.features))
    if p.benefits:
        lines.append("Benefits:\n" + "\n".join(f"- {b}" for b in p.benefits))
    if p.specifications:
        lines.append("Specifications:\n" + "\n".join(f"- {k}: {v}" for k, v in p.specifications.items()))
    if p.variants:
        lines.append("Variants: " + "; ".join(f"{v.name} {v.attributes or ''}" for v in p.variants))
    return "\n".join(lines)


RESEARCH_SCHEMA = """{
  "summary": "2-3 sentence positioning summary",
  "features": [{"feature": "...", "explanation": "..."}],
  "benefits": [{"benefit": "...", "from_feature": "..."}],
  "personas": [{"name": "...", "description": "...", "goals": ["..."], "pain_points": ["..."]}],
  "target_audience": "...",
  "positioning": "...",
  "usps": ["..."],
  "competitor_comparison": [{"competitor": "...", "their_strength": "...", "our_advantage": "...", "gap": "..."}],
  "review_sentiment": {"positive_themes": ["..."], "negative_themes": ["..."], "overall": "positive|mixed|negative|no data"},
  "pain_points": ["..."],
  "objections": [{"objection": "...", "response": "..."}],
  "marketing_angles": [{"angle": "...", "hook": "...", "best_for": "..."}],
  "creative_strategy": {"main_image": "...", "lifestyle": "...", "infographics": ["..."], "video": "..."},
  "assumptions": ["..."]
}"""


def run_research(db: Session, product_id: str, *, reviews: str = "", competitors: str = "", notes: str = "",
                 provider: str | None = None) -> ProductResearch:
    p = db.get(Product, product_id)
    if p is None:
        raise ValueError("product not found")
    brand_txt = brand_context(db, p.brand_id)
    prompt = (
        f"Analyze this product for e-commerce marketing.\n\n{product_facts(p)}\n\n"
        f"{brand_txt and 'Brand profile:' + chr(10) + brand_txt}\n\n"
        f"Customer reviews supplied by the user (may be empty):\n{reviews.strip()[:12000] or '(none provided)'}\n\n"
        f"Competitor information supplied by the user (may be empty):\n{competitors.strip()[:8000] or '(none provided)'}\n\n"
        f"Additional notes: {notes.strip()[:2000] or '(none)'}\n\n"
        "If reviews are not provided, set review_sentiment.overall to 'no data' and leave themes empty. "
        "If competitor info is not provided, return an empty competitor_comparison list. "
        f"Return JSON exactly in this shape:\n{RESEARCH_SCHEMA}"
    )
    res = fm.generate_text(TextRequest(prompt=prompt, system=SYSTEM, json_mode=True, temperature=0.4,
                                       max_tokens=3000), purpose="product_research", preferred=provider)
    data = res.json()
    if not isinstance(data, dict):
        raise ValueError("model returned unexpected JSON")
    r = ProductResearch(product_id=p.id, kind="full", result=data, provider=res.provider, model=res.model,
                        inputs={"reviews_chars": len(reviews), "competitors_chars": len(competitors),
                                "notes": notes[:500], "used_product_fields": [k for k in ("description", "features",
                                "benefits", "specifications") if getattr(p, k)]})
    db.add(r)
    db.flush()
    return r


def listing_prompt(p: Product, brand: Brand | None, brand_txt: str, marketplace: str, opts: dict[str, Any],
                   research: dict[str, Any] | None) -> str:
    lim = limits(marketplace)
    mk = MARKETPLACES.get(marketplace, MARKETPLACES["amazon"])
    research_txt = ""
    if research:
        keep = {k: research.get(k) for k in ("positioning", "usps", "personas", "marketing_angles", "pain_points")}
        research_txt = f"Prior product research (AI-generated, use as guidance):\n{keep}\n\n"
    return (
        f"Write a {mk['label']} product listing.\n"
        f"Country: {opts.get('country', 'US')}. Language: {opts.get('language', 'en')} — write ALL copy in this language.\n"
        f"Target audience override: {opts.get('audience') or '(use brand/product info)'}\n"
        f"Tone: {opts.get('tone') or (brand.tone_of_voice if brand and brand.tone_of_voice else 'clear, confident, benefit-led')}\n"
        f"Seed keywords from user: {opts.get('keywords') or '(none)'}\n\n"
        f"{product_facts(p)}\n\n{brand_txt and 'Brand profile:' + chr(10) + brand_txt + chr(10)}\n{research_txt}"
        "Constraints (guidance):\n"
        f"- title ≤ {lim['title'].get('max_chars')} characters; lead with brand + product type + key differentiator.\n"
        f"- exactly {lim['bullets'].get('count', 5)} bullets, each ≤ {lim['bullets'].get('max_chars')} characters, "
        "starting with a short CAPITALIZED benefit phrase followed by a colon.\n"
        f"- description ≤ {lim['description'].get('max_chars')} characters, plain text paragraphs.\n"
        "- search_terms: space-separated, no brand names, no repetition of title words, ≤ 249 bytes.\n"
        "- Do not claim rankings, certifications or test results that are not in the facts.\n\n"
        "Return JSON exactly:\n"
        '{"title": "...", "bullets": ["..."], "description": "...", "keywords": ["..."], "search_terms": "...", '
        '"benefits": ["..."], "feature_explanations": [{"feature": "...", "explanation": "..."}], '
        '"image_strategy": [{"slot": "main_white|lifestyle|infographic_features|infographic_benefits|comparison|dimensions|detail", '
        '"concept": "...", "headline": "...", "callouts": ["..."]}], '
        '"listing_structure": ["..."], "creative_recommendations": ["..."], "headline": "short 3-7 word image headline", '
        '"subheadline": "...", "assumptions": ["..."]}'
    )


FIELD_PROMPTS = {
    "title": "Rewrite only the title. Return JSON {\"title\": \"...\"}.",
    "bullets": "Rewrite only the bullets. Return JSON {\"bullets\": [\"...\"]}.",
    "description": "Rewrite only the description. Return JSON {\"description\": \"...\"}.",
    "keywords": "Regenerate only keywords and search terms. Return JSON {\"keywords\": [\"...\"], \"search_terms\": \"...\"}.",
    "image_strategy": "Regenerate only image_strategy. Return JSON {\"image_strategy\": [...]}",
}


def generate_listing_copy(db: Session, product_id: str, brand_id: str | None, marketplace: str, opts: dict[str, Any],
                          *, field: str | None = None, current: dict[str, Any] | None = None,
                          provider: str | None = None) -> tuple[dict[str, Any], str, str]:
    p = db.get(Product, product_id)
    if p is None:
        raise ValueError("product not found")
    brand = db.get(Brand, brand_id) if brand_id else None
    research = db.query(ProductResearch).filter(ProductResearch.product_id == p.id) \
        .order_by(ProductResearch.created_at.desc()).first()
    prompt = listing_prompt(p, brand, brand_context(db, brand_id), marketplace, opts,
                            research.result if research else None)
    if field:
        prompt += f"\n\nCurrent draft (keep consistent with it):\n{current or {}}\n\n{FIELD_PROMPTS[field]}"
        if opts.get("instruction"):
            prompt += f"\nUser instruction for this rewrite: {opts['instruction'][:500]}"
    res = fm.generate_text(TextRequest(prompt=prompt, system=SYSTEM, json_mode=True, temperature=0.6, max_tokens=3000),
                           purpose=f"listing_{field or 'copy'}", preferred=provider)
    data = res.json()
    if not isinstance(data, dict):
        raise ValueError("model returned unexpected JSON")
    return data, res.provider, res.model


def creative_prompt(p: Product | None, brand: Brand | None, creative_type: str, style: str, extra: str = "",
                    background_only: bool = True) -> str:
    """Image prompt. In background-only mode the real product photo is composited afterwards."""
    scene = {
        "hero": "product photo backdrop, empty round pedestal, eye-level, soft dramatic light",
        # Close-up of a surface + blurred background makes a composited product look naturally placed.
        "lifestyle": "close-up of an empty tabletop at eye level, blurred cozy interior background, bokeh, warm natural light",
        "studio": "seamless studio backdrop, soft diffused light, empty floor, eye-level",
        "promo": "bold promotional backdrop, dynamic shapes, depth",
        "social": "modern colorful social media backdrop with depth",
        "detail": "macro texture backdrop, soft light",
        "background": "product photography background",
    }.get(creative_type, "product photography background")
    styles = {
        "minimal": "minimal, airy, soft neutral palette", "luxury": "luxury, dark tones, gold accents, moody",
        "natural": "natural materials, wood, linen, plants", "vibrant": "vibrant saturated colors, playful",
        "editorial": "editorial magazine photography, cinematic", "tech": "sleek modern tech aesthetic, cool tones",
    }
    # CLIP-based models (SD/SD-Turbo) read only ~77 tokens, so the most important instructions come FIRST
    # and the prompt is kept short. In background-only mode the product name/category is deliberately NOT
    # mentioned: few-step models ignore negative prompts and would paint extra copies of the product.
    parts = [extra.strip()] if extra.strip() else []
    parts.append(scene)
    if background_only:
        parts.append("empty surface in the center, nothing on it, uncluttered")
    elif p:
        parts.append(f"featuring a {p.category or 'consumer product'}: {p.name}")
    parts.append(styles.get(style, style))
    if background_only and p and p.category:
        parts.append(f"{p.category} setting")
    if brand and brand.aesthetic:
        parts.append(", ".join(brand.aesthetic[:3]).lower())
    parts.append("photorealistic, no text, no watermark" if not background_only else "no text, no people")
    return clip_safe(", ".join(parts))


def clip_safe(prompt: str, max_words: int = 55) -> str:
    """Approximate the 77-token CLIP limit (≈1.3 tokens/word) without loading a tokenizer."""
    words = prompt.split()
    return " ".join(words[:max_words]).rstrip(",")


NEGATIVE = "text, watermark, logo, letters, signature, blurry, lowres, distorted, deformed, extra objects"
