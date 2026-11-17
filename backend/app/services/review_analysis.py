"""AI analysis of ALL stored reviews for a product (map → cluster → count → synthesize).

1. Map: reviews are sent in small batches; the model tags EACH review with short praise / complaint / request labels.
   Small local models stay accurate on 10-15 reviews at a time, and nothing is silently cut off.
2. Cluster: the model groups the free-form labels into a few named themes per kind.
3. Count: Shelfcraft counts how many reviews mention each theme, their average rating and picks real quotes. These
   numbers are computed by code from the per-review tags, not written by the model.
4. Synthesize: one final call turns the counted theme table into pain points, objections, requests and listing advice.

No database session is held during model calls (SQLite allows one writer; long AI calls must not block the app).
"""
from __future__ import annotations

import logging
import random
import re
from collections import Counter, defaultdict
from collections.abc import Callable
from typing import Any

from sqlalchemy import select

from app.ai import fallback_manager as fm
from app.ai.base import NoProviderAvailable, TextRequest
from app.db.models import Product, ProductResearch, ProductReview
from app.db.session import session_scope
from app.services.reviews import review_stats

log = logging.getLogger("shelfcraft.reviews")

BATCH = 12
REVIEW_CHARS = 700
KINDS = ("praise", "complaints", "requests")
SYSTEM = ("You analyse customer reviews for an e-commerce seller. Use ONLY what the reviews say. "
          "Never invent facts, numbers or quotes. Respond with JSON only.")


def _norm_label(s: Any) -> str:
    s = re.sub(r"\s+", " ", str(s or "").strip().lower()).strip(" .,:;-'\"")
    return s[:60]


def stratified_sample(reviews: list[dict[str, Any]], limit: int, seed: int = 7) -> list[dict[str, Any]]:
    """Random sample that keeps the star-rating mix of the full set (so theme percentages stay representative)."""
    if len(reviews) <= limit:
        return reviews
    rng = random.Random(seed)
    groups: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for r in reviews:
        groups[int(round(r["rating"])) if r.get("rating") else None].append(r)
    out: list[dict[str, Any]] = []
    for g in groups.values():
        k = max(1, round(limit * len(g) / len(reviews)))
        out.extend(rng.sample(g, min(k, len(g))))
    return out[:limit]


def _tag_batch(product_line: str, batch: list[dict[str, Any]], provider: str | None) -> tuple[list[dict[str, Any]], str, str]:
    lines = []
    for n, r in enumerate(batch, 1):
        stars = f"{r['rating']:g}★ " if r.get("rating") else ""
        title = f"{r['title']} — " if r.get("title") else ""
        lines.append(f"[{n}] {stars}{title}{(r.get('text') or '')[:REVIEW_CHARS]}")
    prompt = (
        f"Product: {product_line}\n\nReviews:\n" + "\n\n".join(lines) + "\n\n"
        "For EVERY review above, list short theme labels of 2-5 words in lowercase (for example 'lid leaks', "
        "'keeps drinks cold', 'wants a bigger size'). praise = what the customer liked; complaints = problems or "
        "disappointments; requests = things they wish existed or would change. use_case = what they use it for "
        "(2-5 words) or an empty string. Use an empty list when a review has nothing of that kind.\n"
        'Return JSON exactly: {"reviews": [{"n": 1, "praise": ["..."], "complaints": ["..."], "requests": ["..."], '
        '"use_case": "..."}]}'
    )
    res = fm.generate_text(TextRequest(prompt=prompt, system=SYSTEM, json_mode=True, temperature=0.1,
                                       max_tokens=200 + 90 * len(batch)), purpose="review_analysis", preferred=provider)
    data = res.json()
    items = data.get("reviews") if isinstance(data, dict) else data if isinstance(data, list) else None
    if not isinstance(items, list):
        raise ValueError("model returned unexpected JSON")
    out: list[dict[str, Any]] = [{} for _ in batch]
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        n = it.get("n")
        idx = int(n) - 1 if isinstance(n, (int, float)) or (isinstance(n, str) and n.isdigit()) else i
        if 0 <= idx < len(batch):
            out[idx] = {k: [_norm_label(x) for x in (it.get(k) or []) if _norm_label(x)][:6] for k in KINDS}
            out[idx]["use_case"] = _norm_label(it.get("use_case"))
    return out, res.provider, res.model


def _cluster(kind: str, labels: Counter[str], product_line: str, provider: str | None) -> dict[str, str]:
    """Map every label → canonical theme name. Labels the model leaves out keep their own name."""
    if not labels:
        return {}
    top = [lab for lab, _ in labels.most_common(150)]
    if len(top) <= 1:
        return {lab: lab for lab in labels}
    listing = "\n".join(f"- {lab} ({labels[lab]})" for lab in top)
    prompt = (
        f"Product: {product_line}\nThese are '{kind}' labels extracted from customer reviews, with how many reviews "
        f"used each:\n{listing}\n\nGroup labels that mean the same thing into themes (at most 12 themes). Give each "
        "theme a short clear name (2-5 words). Put every label in exactly one theme and copy the labels exactly.\n"
        'Return JSON exactly: {"themes": [{"name": "...", "labels": ["...", "..."]}]}'
    )
    try:
        res = fm.generate_text(TextRequest(prompt=prompt, system=SYSTEM, json_mode=True, temperature=0.1,
                                           max_tokens=2500), purpose="review_analysis", preferred=provider)
        data = res.json()
        themes = data.get("themes") if isinstance(data, dict) else None
    except (NoProviderAvailable, ValueError) as e:
        log.warning("theme clustering failed (%s); using raw labels", e)
        themes = None
    mapping: dict[str, str] = {}
    for t in themes or []:
        if not isinstance(t, dict) or not _norm_label(t.get("name")):
            continue
        for lab in t.get("labels") or []:
            nl = _norm_label(lab)
            if nl in labels and nl not in mapping:
                mapping[nl] = _norm_label(t["name"])
    for lab in labels:
        mapping.setdefault(lab, lab)
    return mapping


def _quote(r: dict[str, Any], words: set[str]) -> str:
    text = r.get("text") or ""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for s in sentences:
        if words & set(re.findall(r"[a-z']+", s.lower())):
            return s[:240]
    return text[:240]


def _theme_table(kind: str, tags: list[dict[str, Any]], sample: list[dict[str, Any]], mapping: dict[str, str]) -> list[dict[str, Any]]:
    members: dict[str, set[int]] = defaultdict(set)
    words: dict[str, set[str]] = defaultdict(set)
    for i, t in enumerate(tags):
        for lab in t.get(kind) or []:
            theme = mapping.get(lab, lab)
            members[theme].add(i)
            words[theme] |= {w for w in re.findall(r"[a-z']+", lab) if len(w) > 3}
    n = len(sample)
    rows = []
    for theme, idx in members.items():
        rated = [sample[i]["rating"] for i in idx if sample[i].get("rating")]
        best = sorted(idx, key=lambda i: -(sample[i].get("helpful_votes") or 0))
        rows.append({"theme": theme, "reviews": len(idx), "share": round(len(idx) / n, 3) if n else 0,
                     "avg_rating": round(sum(rated) / len(rated), 2) if rated else None,
                     "labels": sorted({lab for i in idx for lab in tags[i].get(kind) or [] if mapping.get(lab, lab) == theme})[:8],
                     "quotes": [{"text": _quote(sample[i], words[theme]), "rating": sample[i].get("rating"),
                                 "review_id": sample[i]["id"], **({"competitor": sample[i]["competitor"]}
                                                                  if sample[i].get("competitor") else {})} for i in best[:3]]})
        if any(sample[i].get("competitor") for i in idx):  # competitor reviews: which listings share this theme
            rows[-1]["competitors"] = len({sample[i].get("competitor") for i in idx if sample[i].get("competitor")})
    rows.sort(key=lambda r: (-r["reviews"], r["theme"]))
    return rows[:15]


SYNTH_SCHEMA = """{
  "summary": "3-4 sentences: what customers love, what disappoints them, overall verdict",
  "top_pain_points": [{"pain": "...", "theme": "exact theme name from the table", "how_to_address": "listing/product fix"}],
  "objections": [{"objection": "a doubt a shopper may have before buying", "response": "honest answer based on the reviews"}],
  "buyer_motivations": ["why people buy / what job the product does for them"],
  "feature_requests": ["..."],
  "listing_recommendations": ["concrete changes to title/bullets/description, grounded in the themes"],
  "image_recommendations": ["concrete image/infographic ideas that answer the top concerns"],
  "assumptions": ["anything inferred rather than read in the reviews"]
}"""


def _synthesize(product_line: str, stats: dict[str, Any], themes: dict[str, list[dict[str, Any]]],
                use_cases: list[tuple[str, int]], analysed: int, provider: str | None) -> tuple[dict[str, Any], str, str]:
    def table(rows: list[dict[str, Any]]) -> str:
        return "\n".join(f"- {r['theme']}: {r['reviews']} of {analysed} reviews ({r['share']:.0%}), avg rating "
                         f"{r['avg_rating'] if r['avg_rating'] is not None else 'n/a'}; e.g. \"{r['quotes'][0]['text'][:160] if r['quotes'] else ''}\""
                         for r in rows[:10]) or "(none)"
    hist = ", ".join(f"{k}★: {v}" for k, v in stats["histogram"].items())
    prompt = (
        f"Product: {product_line}\nReview set: {stats['count']} reviews, average {stats['average']}, ratings {hist}. "
        f"{analysed} reviews were tagged.\n\nWhat customers PRAISE (counted):\n{table(themes['praise'])}\n\n"
        f"What customers COMPLAIN about (counted):\n{table(themes['complaints'])}\n\n"
        f"What customers REQUEST:\n{table(themes['requests'])}\n\n"
        f"Use cases mentioned: {', '.join(f'{u} ({c})' for u, c in use_cases[:12]) or '(none)'}\n\n"
        "Write seller-facing conclusions. Base every point on the counted themes above and prioritise by how many "
        f"reviews mention it. Return JSON exactly in this shape:\n{SYNTH_SCHEMA}"
    )
    res = fm.generate_text(TextRequest(prompt=prompt, system=SYSTEM, json_mode=True, temperature=0.3, max_tokens=2200),
                           purpose="review_analysis", preferred=provider)
    data = res.json()
    if not isinstance(data, dict):
        raise ValueError("model returned unexpected JSON")
    return data, res.provider, res.model


def analyze_product_reviews(product_id: str, *, provider: str | None = None, max_reviews: int = 400,
                            progress: Callable[[float, str], None] = lambda f, m: None) -> str:
    """Run the full analysis and store it as ProductResearch(kind='reviews'). Returns the research id."""
    with session_scope() as db:
        p = db.get(Product, product_id)
        if p is None:
            raise ValueError("product not found")
        product_line = f"{p.name}" + (f" (category: {p.category})" if p.category else "")
        rows = db.scalars(select(ProductReview).where(ProductReview.product_id == product_id)).all()
        reviews = [{"id": r.id, "rating": r.rating, "title": r.title, "text": r.text, "variant": r.variant,
                    "review_date": r.review_date, "verified": r.verified, "helpful_votes": r.helpful_votes,
                    "source": r.source} for r in rows]
    if not reviews:
        raise ValueError("no reviews stored for this product yet; add review pages, a CSV export or pasted reviews first")
    stats = review_stats(reviews)
    sample = stratified_sample(reviews, max_reviews)
    batches = [sample[i:i + BATCH] for i in range(0, len(sample), BATCH)]
    tags: list[dict[str, Any]] = []
    tagged_sample: list[dict[str, Any]] = []
    used: Counter[tuple[str, str]] = Counter()
    ai_error: str | None = None
    for bi, batch in enumerate(batches):
        progress(0.05 + 0.75 * bi / len(batches), f"Reading reviews {bi * BATCH + 1}-{bi * BATCH + len(batch)} of {len(sample)}")
        result = None
        for _attempt in range(2):
            try:
                result = _tag_batch(product_line, batch, provider)
                break
            except NoProviderAvailable as e:
                ai_error = str(e)
                break
            except ValueError as e:
                log.warning("review batch %s failed: %s", bi, e)
        if ai_error and not tags:
            break  # no AI at all: store the exact statistics only
        if result is None:
            continue
        batch_tags, prov, model = result
        used[(prov, model)] += 1
        for r, t in zip(batch, batch_tags, strict=True):
            if t:
                tags.append(t)
                tagged_sample.append(r)

    themes: dict[str, list[dict[str, Any]]] = {k: [] for k in KINDS}
    use_cases: list[tuple[str, int]] = []
    synthesis: dict[str, Any] = {}
    if tags:
        progress(0.82, "Grouping themes")
        for kind in KINDS:
            labels = Counter(lab for t in tags for lab in t.get(kind) or [])
            themes[kind] = _theme_table(kind, tags, tagged_sample, _cluster(kind, labels, product_line, provider))
        use_cases = Counter(t["use_case"] for t in tags if t.get("use_case")).most_common(15)
        progress(0.92, "Writing conclusions")
        try:
            synthesis, prov, model = _synthesize(product_line, stats, themes, use_cases, len(tags), provider)
            used[(prov, model)] += 1
        except (NoProviderAvailable, ValueError) as e:
            log.warning("review synthesis failed: %s", e)
            synthesis = {"summary": "", "assumptions": [f"The final summary step failed ({e}); the counted themes are complete."]}
    (prov, model), _ = used.most_common(1)[0] if used else ((None, None), 0)
    result = {
        "stats": stats, "themes": themes,
        "use_cases": [{"use_case": u, "reviews": c} for u, c in use_cases],
        **synthesis,
        "coverage": {"total_reviews": len(reviews), "sampled": len(sample), "analysed": len(tags),
                     "skipped": len(sample) - len(tags),
                     "sample_note": (f"A random sample of {len(sample)} of {len(reviews)} reviews (same star-rating mix) was "
                                     "tagged by AI; star statistics and phrases use all reviews.") if len(sample) < len(reviews) else None,
                     "ai_error": ai_error if not tags else None},
    }
    with session_scope() as db:
        r = ProductResearch(product_id=product_id, kind="reviews", result=result, provider=prov, model=model,
                            inputs={"reviews": len(reviews), "analysed": len(tags), "max_reviews": max_reviews})
        db.add(r)
        db.flush()
        return r.id


def latest_review_summary(db: Any, product_id: str) -> str:
    """Compact text of the latest review analysis, for other prompts (listing copy, full research)."""
    r = db.scalars(select(ProductResearch).where(ProductResearch.product_id == product_id, ProductResearch.kind == "reviews")
                   .order_by(ProductResearch.created_at.desc()).limit(1)).first()
    if not r or not r.result.get("coverage", {}).get("analysed"):
        return ""
    res = r.result
    n = res["coverage"]["analysed"]

    def rows(kind: str) -> str:
        return "; ".join(f"{t['theme']} ({t['reviews']}/{n})" for t in res["themes"].get(kind, [])[:8]) or "none"
    return (f"Analysis of {res['stats']['count']} customer reviews (average {res['stats']['average']}★): "
            f"praised: {rows('praise')}. Complaints: {rows('complaints')}. Requests: {rows('requests')}.")
