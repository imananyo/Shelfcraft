"""AI category analysis: what top-performing listings do, where competitors are weak, how to win.

Inputs (all collected by the user from pages they opened themselves): competitor listings (Best Sellers / search /
product pages) and the reviews on competitor product pages.

1. Exact benchmark (competitors.benchmark): prices, ratings, review counts, title length, shared title keywords.
2. Competitor reviews are tagged in batches and grouped into counted themes, exactly like the product's own reviews:
   "lid leaks: 31 of 120 competitor reviews, across 6 listings" = a market-wide weakness you can win on.
3. One synthesis call turns the numbers into patterns, a title formula, weaknesses and recommendations.
   Keyword suggestions are restricted to terms that really appear in top titles and are missing from yours.
"""
from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable
from typing import Any

from sqlalchemy import select

from app.ai import fallback_manager as fm
from app.ai.base import NoProviderAvailable, TextRequest
from app.db.models import CompetitorListing, Product, ProductResearch
from app.db.session import session_scope
from app.services.competitors import benchmark, competitor_out
from app.services.review_analysis import BATCH, KINDS, SYSTEM, _cluster, _tag_batch, _theme_table, stratified_sample

log = logging.getLogger("shelfcraft.category")

SCHEMA = """{
  "summary": "3-4 sentences: what wins in this category and where the opening is",
  "what_top_listings_do": ["pattern seen across several top listings"],
  "title_formula": "the structure top titles follow, e.g. Brand + product type + key spec + size + use",
  "bullet_patterns": ["how top listings structure and phrase their bullets"],
  "image_patterns": ["what their images / video / A+ do (from the numbers)"],
  "price_positioning": "where the user's price sits and what that means",
  "competitor_weaknesses": [{"weakness": "...", "evidence": "theme + count or listing", "opportunity": "how the user can win"}],
  "differentiation_angles": [{"angle": "...", "why": "..."}],
  "keywords_to_add": ["only terms from the MISSING KEYWORDS list"],
  "listing_recommendations": ["concrete changes to the user's title/bullets/images"],
  "assumptions": ["anything inferred rather than read in the data"]
}"""


def _product_dict(p: Product) -> dict[str, Any]:
    return {"name": p.name, "price": p.price, "description": p.description, "features": p.features or [],
            "bullets": p.benefits or [], "category": p.category, "brand": (p.specifications or {}).get("Brand")}


def analyze_category(product_id: str, *, provider: str | None = None, max_reviews: int = 120,
                     progress: Callable[[float, str], None] = lambda f, m: None) -> str:
    from app.services.copywriting import product_facts
    from app.services.review_analysis import latest_review_summary

    with session_scope() as db:
        p = db.get(Product, product_id)
        if p is None:
            raise ValueError("product not found")
        mine = _product_dict(p)
        facts = product_facts(p)
        own_reviews = latest_review_summary(db, product_id)
        rows = db.scalars(select(CompetitorListing).where(CompetitorListing.product_id == product_id,
                                                          CompetitorListing.included.is_(True))).all()
        comps = [{**competitor_out(c), "reviews": c.reviews or []} for c in rows]
    if not comps:
        raise ValueError("no competitor listings collected yet; save a Best Sellers or search results page first")
    bench = benchmark(mine, comps)
    category = (bench["categories"] or [mine["category"] or "this category"])[0].removeprefix("Search: ")
    product_line = f"competing products in {category}"

    # ---- competitor reviews → counted themes
    pool = [{"id": f"{c['id']}:{i}", "competitor": (c.get("title") or c["market_id"])[:70], **r}
            for c in comps for i, r in enumerate(c["reviews"]) if r.get("text")]
    sample = stratified_sample(pool, max_reviews)
    tags: list[dict[str, Any]] = []
    tagged: list[dict[str, Any]] = []
    used: Counter[tuple[str, str]] = Counter()
    ai_error = None
    batches = [sample[i:i + BATCH] for i in range(0, len(sample), BATCH)]
    for bi, batch in enumerate(batches):
        progress(0.05 + 0.6 * bi / max(len(batches), 1), f"Reading competitor reviews {bi * BATCH + 1}-{bi * BATCH + len(batch)} of {len(sample)}")
        try:
            batch_tags, prov, model = _tag_batch(product_line, batch, provider)
        except NoProviderAvailable as e:
            ai_error = str(e)
            break
        except ValueError as e:
            log.warning("competitor review batch failed: %s", e)
            continue
        used[(prov, model)] += 1
        for r, t in zip(batch, batch_tags, strict=True):
            if t:
                tags.append(t)
                tagged.append(r)
    themes: dict[str, list[dict[str, Any]]] = {k: [] for k in KINDS}
    if tags:
        progress(0.7, "Grouping competitor review themes")
        for kind in KINDS:
            labels = Counter(lab for t in tags for lab in t.get(kind) or [])
            themes[kind] = _theme_table(kind, tags, tagged, _cluster(kind, labels, product_line, provider))

    # ---- synthesis
    synthesis: dict[str, Any] = {}
    if not ai_error:
        progress(0.85, "Comparing with top listings")
        try:
            synthesis, prov, model = _synthesize(facts, own_reviews, bench, comps, themes, len(tags), provider)
            used[(prov, model)] += 1
        except NoProviderAvailable as e:
            ai_error = str(e)
        except ValueError as e:
            log.warning("category synthesis failed: %s", e)
            synthesis = {"assumptions": [f"The final AI step failed ({e}); the benchmark numbers are complete."]}
    missing = set(bench["missing_keywords"])
    if synthesis.get("keywords_to_add"):
        synthesis["keywords_to_add"] = [k for k in synthesis["keywords_to_add"] if isinstance(k, str) and k.lower() in missing]
    (prov, model), _ = used.most_common(1)[0] if used else ((None, None), 0)
    result = {"benchmark": bench, "competitor_review_themes": themes, **synthesis,
              "coverage": {"listings": len(comps), "with_details": bench["with_details"], "competitor_reviews": len(pool),
                           "reviews_analysed": len(tags), "ai_error": ai_error}}
    with session_scope() as db:
        r = ProductResearch(product_id=product_id, kind="category", result=result, provider=prov, model=model,
                            inputs={"listings": len(comps), "competitor_reviews": len(pool), "analysed": len(tags)})
        db.add(r)
        db.flush()
        return r.id


def _synthesize(facts: str, own_reviews: str, bench: dict[str, Any], comps: list[dict[str, Any]],
                themes: dict[str, list[dict[str, Any]]], analysed: int, provider: str | None) -> tuple[dict[str, Any], str, str]:
    def q(d: dict[str, Any] | None, unit: str = "") -> str:
        return f"median {d['median']}{unit} (range {d['min']}-{d['max']}, n={d['n']})" if d else "n/a"

    top_lines = []
    for c in comps[:12]:
        bits = [f"{c.get('title') or c['market_id']}"[:150]]
        for k, label in (("price", "price"), ("rating", "rating"), ("review_count", "reviews"), ("monthly_bought", "bought/month"),
                         ("rank", "best-seller rank"), ("position", "search position")):
            if c.get(k) is not None:
                bits.append(f"{label} {c[k]}")
        if c.get("sponsored"):
            bits.append("sponsored")
        if c.get("bullets"):
            bits.append("bullets: " + " | ".join(b[:110] for b in c["bullets"][:3]))
        top_lines.append("- " + "; ".join(bits))
    comp_themes = "\n".join(
        f"- {t['theme']}: {t['reviews']} of {analysed} competitor reviews, {t.get('competitors', '?')} listings"
        for t in themes["complaints"][:8]) or "(no competitor reviews collected)"
    kw = ", ".join(f"{k['term']} ({k['titles']} titles)" for k in bench["keywords"][:20])
    prompt = (
        f"YOUR PRODUCT:\n{facts[:2500]}\n\n"
        + (f"YOUR OWN REVIEWS: {own_reviews}\n\n" if own_reviews else "")
        + f"CATEGORY BENCHMARK ({bench['listings']} top listings collected):\n"
        f"- price {q(bench['price'])}; your price {bench['your_price']}\n- rating {q(bench['rating'])}\n"
        f"- review count {q(bench['review_count'])}\n- title length {q(bench['title_chars'], ' chars')}\n"
        f"- images {q(bench['images'])}; video on {bench['video_share']}; A+ on {bench['aplus_share']} of detailed listings\n"
        f"- common title keywords: {kw or 'n/a'}\n- MISSING KEYWORDS (in top titles, not in your listing): "
        f"{', '.join(bench['missing_keywords']) or 'none'}\n\nTOP LISTINGS:\n" + "\n".join(top_lines) + "\n\n"
        f"COMPETITOR COMPLAINTS (counted from their reviews):\n{comp_themes}\n\n"
        "Compare the user's product with these top listings. Ground every point in the numbers and listings above. "
        "Never recommend putting competitor brand names, product-line names or model numbers into the user's listing "
        "(marketplace rules forbid it), and do not claim the user's product has features that are not in YOUR PRODUCT. "
        f"Return JSON exactly in this shape:\n{SCHEMA}"
    )
    res = fm.generate_text(TextRequest(prompt=prompt, system=SYSTEM, json_mode=True, temperature=0.3, max_tokens=2200),
                           purpose="category_analysis", preferred=provider)
    data = res.json()
    if not isinstance(data, dict):
        raise ValueError("model returned unexpected JSON")
    return data, res.provider, res.model


def latest_category_summary(db: Any, product_id: str) -> str:
    """Compact text for other prompts (product research, listing copy). Falls back to the raw benchmark."""
    r = db.scalars(select(ProductResearch).where(ProductResearch.product_id == product_id, ProductResearch.kind == "category")
                   .order_by(ProductResearch.created_at.desc()).limit(1)).first()
    if r is None:
        return ""
    res, b = r.result, r.result.get("benchmark", {})
    parts = [f"{b.get('listings')} top listings in the category"]
    if b.get("price"):
        parts.append(f"median price {b['price']['median']}")
    if b.get("title_chars"):
        parts.append(f"median title length {b['title_chars']['median']} chars")
    if b.get("missing_keywords"):
        parts.append("title keywords top listings use that this listing lacks: " + ", ".join(b["missing_keywords"][:12]))
    weak = [w.get("weakness") for w in res.get("competitor_weaknesses") or [] if isinstance(w, dict)]
    if weak:
        parts.append("competitor weaknesses: " + "; ".join(str(x) for x in weak[:5]))
    if res.get("title_formula"):
        parts.append(f"title formula in the category: {res['title_formula']}")
    return ". ".join(parts) + "."
