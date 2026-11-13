"""Listing Grader: transparent, rule-based scoring of a marketplace listing + optional AI critique.

Every check states what it measured and how to fix it. Scores are guidance derived from commonly
published seller recommendations — not a prediction of rank or a marketplace compliance verdict.
"""
from __future__ import annotations

import re
from typing import Any

import numpy as np
from PIL import Image

from app.services.marketplaces import MARKETPLACES

PROMO_WORDS = {"best", "#1", "number one", "free shipping", "sale", "discount", "cheapest", "guaranteed", "100%",
               "top rated", "hot", "deal", "limited time", "bestseller", "best seller"}
WEIGHTS = {"title": 25, "bullets": 25, "description": 10, "search_terms": 10, "images": 25, "aplus": 5}


def _check(label: str, ok: bool, points: float, fix: str, detail: str = "", severity: str = "warn") -> dict[str, Any]:
    return {"label": label, "passed": ok, "points": points if ok else 0, "max": points, "detail": detail,
            "fix": "" if ok else fix, "severity": "ok" if ok else severity}


def _words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", s.lower())


def grade_title(title: str, brand: str | None, keywords: list[str], marketplace: str) -> dict[str, Any]:
    lim = MARKETPLACES.get(marketplace, MARKETPLACES["amazon"])["fields"]["title"].get("max_chars", 200)
    n = len(title)
    lower = title.lower()
    checks = [
        _check("Title present", n > 0, 4, "Add a product title.", severity="error"),
        _check(f"Length within {lim} characters", 0 < n <= lim, 5, f"Shorten the title to ≤ {lim} characters.", f"{n} characters"),
        _check("Descriptive length (≥ 50 characters)", n >= 50, 4, "Add product type, key feature, size/quantity.", f"{n} characters"),
        _check("Leads with the brand", bool(brand) and lower.startswith(brand.lower()) if brand else True, 3,
               f"Start the title with your brand name ({brand}).", ""),
        _check("No promotional claims", not any(w in lower for w in PROMO_WORDS), 4,
               "Remove promotional words (best, sale, free shipping, #1…).",
               ", ".join(sorted(w for w in PROMO_WORDS if w in lower))),
        _check("Not in ALL CAPS", not (title.isupper() and n > 10), 2, "Use title case instead of all caps."),
        _check("No repeated words", len(_words(title)) - len(set(_words(title))) <= 2, 2, "Remove repeated words.",
               f"{len(_words(title)) - len(set(_words(title)))} repeats"),
    ]
    if keywords:
        hit = [k for k in keywords[:5] if k.lower() in lower]
        checks.append(_check("Contains a primary keyword", bool(hit), 1, f"Work your top keyword ({keywords[0]}) into the title.",
                             ", ".join(hit)))
    return _section("title", checks)


def grade_bullets(bullets: list[str], marketplace: str) -> dict[str, Any]:
    f = MARKETPLACES.get(marketplace, MARKETPLACES["amazon"])["fields"]["bullets"]
    want, lim = f.get("count", 5), f.get("max_chars", 255)
    bullets = [b for b in bullets if b.strip()]
    lens = [len(b) for b in bullets]
    headers = [b for b in bullets if re.match(r"^[A-Z0-9][A-Z0-9 &'\-/]{2,40}[:—–-]", b.strip())]
    checks = [
        _check(f"{want} bullet points", len(bullets) >= want, 8, f"Write {want} bullets (you have {len(bullets)}).", f"{len(bullets)} bullets",
               severity="error" if not bullets else "warn"),
        _check(f"Each bullet ≤ {lim} characters", all(n <= lim for n in lens), 5, f"Trim bullets longer than {lim} characters.",
               f"longest {max(lens) if lens else 0}"),
        _check("Bullets are substantial (≥ 60 characters)", bool(lens) and min(lens) >= 60, 4, "Expand short bullets with a benefit + proof.",
               f"shortest {min(lens) if lens else 0}"),
        _check("Benefit-first headers (e.g. 'LEAKPROOF:')", len(headers) >= max(1, len(bullets) - 1), 4,
               "Start each bullet with a short capitalized benefit followed by a colon.", f"{len(headers)}/{len(bullets)}"),
        _check("No promotional claims", not any(w in " ".join(bullets).lower() for w in PROMO_WORDS), 4,
               "Remove promotional/unverifiable claims from bullets."),
    ]
    return _section("bullets", checks)


def grade_description(desc: str, marketplace: str) -> dict[str, Any]:
    lim = MARKETPLACES.get(marketplace, MARKETPLACES["amazon"])["fields"]["description"].get("max_chars", 2000)
    n = len(desc)
    checks = [
        _check("Description present", n > 0, 3, "Add a product description.", severity="error"),
        _check("At least 300 characters", n >= 300, 3, "Expand the description (story, use cases, care).", f"{n} characters"),
        _check(f"Within {lim} characters", n <= lim, 2, f"Shorten to ≤ {lim} characters.", f"{n} characters"),
        _check("Readable paragraphs", desc.count("\n") >= 1 or n < 600, 2, "Break long text into short paragraphs."),
    ]
    return _section("description", checks)


def grade_search_terms(terms: str, title: str, brand: str | None, marketplace: str) -> dict[str, Any]:
    f = MARKETPLACES.get(marketplace, MARKETPLACES["amazon"])["fields"]["search_terms"]
    nbytes = len(terms.encode())
    limit_b = f.get("max_bytes")
    words = _words(terms)
    title_words = set(_words(title))
    dup_title = [w for w in set(words) if w in title_words and len(w) > 3]
    checks = [
        _check("Search terms present", bool(terms.strip()), 3, "Add backend search terms (synonyms, uses, misspellings)."),
        _check(f"Within {limit_b} bytes" if limit_b else "Reasonable length", nbytes <= (limit_b or 500), 3,
               f"Trim to ≤ {limit_b} bytes — extra text may be ignored.", f"{nbytes} bytes"),
        _check("No brand names", not brand or brand.lower() not in terms.lower(), 2, "Remove brand names from search terms."),
        _check("Doesn't repeat title words", len(dup_title) <= 2, 1, "Use new words instead of repeating title words.", ", ".join(dup_title[:8])),
        _check("No duplicate words", len(words) == len(set(words)), 1, "Remove duplicate words."),
    ]
    return _section("search_terms", checks)


def image_facts(im: Image.Image) -> dict[str, Any]:
    rgb = np.asarray(im.convert("RGB").resize((256, max(1, int(256 * im.height / im.width)))))
    h, w = rgb.shape[:2]
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    white_border = float((border.min(axis=1) >= 245).mean())
    non_white = (rgb.min(axis=2) < 240)
    ys, xs = np.nonzero(non_white)
    fill = 0.0
    if len(xs):
        fill = float(((xs.max() - xs.min()) * (ys.max() - ys.min())) / (w * h))
    return {"width": im.width, "height": im.height, "white_border": round(white_border, 3), "subject_fill": round(fill, 3)}


def grade_images(images: list[Image.Image], marketplace: str) -> dict[str, Any]:
    facts = [image_facts(im) for im in images]
    main = facts[0] if facts else None
    hi_res = [f for f in facts if min(f["width"], f["height"]) >= 1000]
    checks = [
        _check("At least 1 image", bool(facts), 4, "Add product images.", severity="error"),
        _check("6+ images", len(facts) >= 6, 5, "Aim for 6–9 images: main, lifestyle, infographics, comparison, size.", f"{len(facts)} images"),
        _check("Main image on pure white", bool(main) and main["white_border"] >= 0.97, 6,
               "Use a pure-white (255,255,255) background for the main image (Image studio → White-background main).",
               f"{round((main or {}).get('white_border', 0) * 100)}% white border" if main else ""),
        _check("Product fills ~85% of the main image", bool(main) and 0.6 <= main["subject_fill"] <= 0.95, 4,
               "Crop so the product fills most of the frame.", f"{round((main or {}).get('subject_fill', 0) * 100)}% fill" if main else ""),
        _check("All images ≥ 1000 px (zoom)", bool(facts) and len(hi_res) == len(facts), 4, "Use images at least 1000 px on the short side.",
               f"{len(hi_res)}/{len(facts)} high-res"),
        _check("Includes non-main images", len(facts) >= 2, 2, "Add lifestyle and infographic images."),
    ]
    sec = _section("images", checks)
    sec["facts"] = facts
    return sec


def grade_aplus(has_aplus: bool) -> dict[str, Any]:
    return _section("aplus", [_check("A+ content", has_aplus, 5, "Add A+ content (A+ content → New A+ layout).")])


def _section(key: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
    got, mx = sum(c["points"] for c in checks), sum(c["max"] for c in checks) or 1
    return {"key": key, "score": round(100 * got / mx), "checks": checks}


def grade(listing: dict[str, Any], images: list[Image.Image], *, marketplace: str = "amazon", brand: str | None = None,
          has_aplus: bool = False) -> dict[str, Any]:
    keywords = listing.get("keywords") or []
    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(",") if k.strip()]
    sections = [
        grade_title(listing.get("title") or "", brand, keywords, marketplace),
        grade_bullets(listing.get("bullets") or [], marketplace),
        grade_description(listing.get("description") or "", marketplace),
        grade_search_terms(listing.get("search_terms") or "", listing.get("title") or "", brand, marketplace),
        grade_images(images, marketplace),
        grade_aplus(has_aplus),
    ]
    total = round(sum(s["score"] * WEIGHTS[s["key"]] for s in sections) / sum(WEIGHTS.values()))
    fixes = [c | {"section": s["key"]} for s in sections for c in s["checks"] if not c["passed"]]
    fixes.sort(key=lambda c: (c["severity"] != "error", -c["max"]))
    grade_letter = "A" if total >= 90 else "B" if total >= 80 else "C" if total >= 65 else "D" if total >= 50 else "F"
    return {"score": total, "grade": grade_letter, "sections": sections, "top_fixes": fixes[:8], "marketplace": marketplace,
            "note": "Rule-based guidance from commonly published seller recommendations. Not a ranking prediction or compliance check."}


def ai_critique(listing: dict[str, Any], marketplace: str) -> dict[str, Any]:
    """Optional LLM review. Raises NoProviderAvailable when no free/local text model is reachable."""
    from app.ai import fallback_manager as fm
    from app.ai.base import TextRequest

    prompt = (f"You are an experienced {MARKETPLACES.get(marketplace, MARKETPLACES['amazon'])['label']} listing reviewer. "
              "Review this listing for clarity, persuasiveness and customer questions it leaves unanswered. Do not invent facts.\n\n"
              f"Title: {listing.get('title', '')}\nBullets:\n" + "\n".join(f"- {b}" for b in listing.get("bullets") or [])
              + f"\nDescription: {(listing.get('description') or '')[:2500]}\n\n"
              'Return JSON: {"strengths": ["..."], "weaknesses": ["..."], "rewrite_suggestions": [{"field": "title|bullets|description", '
              '"suggestion": "..."}], "unanswered_questions": ["..."]}')
    res = fm.generate_text(TextRequest(prompt=prompt, json_mode=True, temperature=0.3, max_tokens=1200), purpose="listing_grader")
    data = res.json()
    return {**(data if isinstance(data, dict) else {}), "provider": res.provider, "model": res.model}
