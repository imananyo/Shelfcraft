"""Analyse → plan → render, step 1 and 2: the creative brief and the per-slot image plan.

* The **creative brief** gathers everything known about a product (facts, Deep Strategy, review themes, category
  benchmark) plus a short AI pass for the hook, concept and customer needs. It is saved as a ProductResearch row
  (kind "brief") together with the ids of the sources it was built from, and reused until one of them changes.
* The **image plan** is written from that brief and the brand rules, one small AI call per image slot (small local
  models can't produce one huge reliable JSON answer). Each slot records which part of the strategy it uses, and is
  checked against the brand's banned words. If the AI is unavailable or answers badly, a slot falls back to the
  listing copy's image strategy / the brief, and is marked as such. The plan is editable before rendering.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import UTC, datetime
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import fallback_manager as fm
from app.ai.base import NoProviderAvailable, TextRequest
from app.db.models import Brand, Product, ProductResearch, Project
from app.services.brand_rules import banned_hits, clean_rules, rules_text
from app.services.marketplaces import MARKETPLACES

log = logging.getLogger("shelfcraft.plan")

# ProductResearch kinds that are not the "full" Deep Strategy result.
NON_STRATEGY_KINDS = ("reviews", "category", "brief")
SOURCES = ("hook", "pain_point", "usp", "benefit", "persona", "review", "spec")
EDITABLE = ("purpose", "concept", "headline", "callouts", "people", "strategy_source", "strategy_note")

SLOT_GUIDE: dict[str, tuple[str, bool]] = {  # slot -> (purpose, carries on-image text)
    "main_white": ("Marketplace main image: the product alone on pure white. No text, no props, no people.", False),
    "lifestyle": ("Lifestyle scene: the product in real use, in the setting of the target customer.", True),
    "lifestyle_2": ("Second lifestyle / premium hero scene from a different angle or moment than the first.", True),
    "infographic_features": ("Feature callouts: the product with short labels for its most important features.", True),
    "infographic_benefits": ("Benefit image: one emotional benefit as a headline over a lifestyle scene.", True),
    "comparison": ("Comparison: why this product beats the usual alternative (addresses a pain point).", True),
    "dimensions": ("Size and dimensions: exact measurements from the specs.", True),
    "detail": ("Close-up detail: material, texture or build quality that proves a claim.", True),
}

# Values are "..." on purpose: small local models copy instruction text placed inside JSON values.
BRIEF_SCHEMA = """{"hook": "...", "creative_concept": "...", "target": "...",
  "customer_needs": [{"feature": "...", "functional_benefit": "...", "emotional_benefit": "...", "problem_solved": "..."}]}"""
BRIEF_FIELDS = ("hook = the single most compelling reason to buy, one sentence; creative_concept = the visual idea that ties "
                "the image set together, one sentence; target = who the images speak to.")

SLOT_SCHEMA = """{"purpose": "...", "concept": "...", "headline": "...", "callouts": ["..."], "people": false}"""
SLOT_FIELDS = ("purpose = what this image makes the shopper understand; concept = the scene and background only, at most "
               "30 words, no text, no product name; headline = shown on the image; callouts = short labels shown on the "
               "image; people = true only if a person should appear in the scene.")
# Strategy points each slot should prove, in order of preference. Shelfcraft assigns them (small models given a
# "pick a different point" instruction pick the same one for every image).
SLOT_FOCUS = {"lifestyle": ("hook", "persona", "benefit"), "lifestyle_2": ("review", "persona", "benefit"),
              "infographic_features": ("usp", "benefit"), "infographic_benefits": ("benefit", "review", "hook"),
              "comparison": ("pain_point", "usp"), "detail": ("usp", "benefit", "review"), "dimensions": ("spec",),
              "main_white": ()}
_ECHO = re.compile(r"^\s*(one|a|short|max(imum)?\s+\d+\s+words?|the single most[^:]*|\.\.\.)\s*(sentence)?\s*[:\-–]\s*", re.I)


def strip_echo(v: Any) -> str:
    """Remove schema/instruction text a small model copied into its answer (e.g. "one sentence: ...")."""
    return _ECHO.sub("", str(v or "")).strip()

SYSTEM = ("You are a senior Amazon listing creative director. Use ONLY the facts provided; never invent "
          "certifications, results or specs. Respond with JSON only.")


# ---------------------------------------------------------------- sources
def _latest(db: Session, product_id: str, kinds: tuple[str, ...] | None = None, exclude: tuple[str, ...] = ()) -> ProductResearch | None:
    q = select(ProductResearch).where(ProductResearch.product_id == product_id)
    if kinds:
        q = q.where(ProductResearch.kind.in_(kinds))
    if exclude:
        q = q.where(ProductResearch.kind.notin_(exclude))
    return db.scalars(q.order_by(ProductResearch.created_at.desc()).limit(1)).first()


def latest_strategy(db: Session, product_id: str) -> ProductResearch | None:
    """Latest Deep Strategy ("full" research) result."""
    return _latest(db, product_id, exclude=NON_STRATEGY_KINDS)


def _sources(db: Session, p: Product) -> dict[str, Any]:
    from app.services.copywriting import product_facts

    strat, rev, cat = latest_strategy(db, p.id), _latest(db, p.id, ("reviews",)), _latest(db, p.id, ("category",))
    return {"strategy_id": strat.id if strat else None, "reviews_id": rev.id if rev else None,
            "category_id": cat.id if cat else None,
            "facts_hash": hashlib.sha1(product_facts(p).encode()).hexdigest()[:16]}


def _themes(rev: ProductResearch | None, kind: str, n: int = 5) -> list[str]:
    if not rev:
        return []
    themes = ((rev.result or {}).get("themes") or {}).get(kind) or []
    return [str(t.get("theme")) for t in themes[:n] if isinstance(t, dict) and t.get("theme")]


def _strategy_part(strat: ProductResearch | None) -> dict[str, Any]:
    r = (strat.result if strat else None) or {}
    personas = [{"name": x.get("name"), "pain_points": x.get("pain_points") or []}
                for x in (r.get("personas") or []) if isinstance(x, dict)][:3]
    angles = [{"angle": x.get("angle"), "hook": x.get("hook")} for x in (r.get("marketing_angles") or []) if isinstance(x, dict)][:4]
    cs = r.get("creative_strategy") if isinstance(r.get("creative_strategy"), dict) else {}
    return {"positioning": r.get("positioning") or r.get("summary") or "", "usps": [str(u) for u in (r.get("usps") or [])][:6],
            "pain_points": [str(x) for x in (r.get("pain_points") or [])][:6], "personas": personas,
            "marketing_angles": angles, "creative_strategy": cs,
            "objections": [x.get("objection") for x in (r.get("objections") or []) if isinstance(x, dict) and x.get("objection")][:4]}


# ---------------------------------------------------------------- brief
def build_brief(db: Session, product_id: str, provider: str | None = None) -> ProductResearch:
    from app.routers.brands import brand_context
    from app.services.category_analysis import latest_category_summary
    from app.services.copywriting import product_facts

    p = db.get(Product, product_id)
    if p is None:
        raise ValueError("product not found")
    sources = _sources(db, p)
    strat = db.get(ProductResearch, sources["strategy_id"]) if sources["strategy_id"] else None
    rev = db.get(ProductResearch, sources["reviews_id"]) if sources["reviews_id"] else None
    strategy = _strategy_part(strat)
    reviews = {"love": _themes(rev, "praise"), "hate": _themes(rev, "complaints"), "requests": _themes(rev, "requests", 3)}
    category = latest_category_summary(db, p.id) if sources["category_id"] else ""
    brief: dict[str, Any] = {"product": {"name": p.name, "category": p.category, "features": list(p.features or [])[:8],
                                         "benefits": list(p.benefits or [])[:8],
                                         "specifications": dict(list((p.specifications or {}).items())[:12])},
                             "strategy": strategy, "reviews": reviews, "category_benchmark": category[:1500]}
    prompt = (f"Write the creative brief for this product's listing images.\n\n{product_facts(p)}\n\n"
              f"{brand_context(db, p.brand_id)}\n\nDeep Strategy: {strategy}\n\n"
              f"What customers love: {reviews['love'] or '(no review data)'}\nWhat they complain about: "
              f"{reviews['hate'] or '(no review data)'}\n" + (f"Category benchmark: {category[:1200]}\n" if category else "") +
              f"\n{BRIEF_FIELDS} customer_needs: 3 to 5 items, each tied to a real feature from the facts.\n"
              f"Return JSON exactly in this shape:\n{BRIEF_SCHEMA}")
    llm: dict[str, Any] = {}
    provider_used = model_used = None
    try:
        res = fm.generate_text(TextRequest(prompt=prompt, system=SYSTEM, json_mode=True, temperature=0.4, max_tokens=900),
                               purpose="creative_brief", preferred=provider)
        data = res.json()
        if isinstance(data, dict):
            llm, provider_used, model_used = data, res.provider, res.model
    except (NoProviderAvailable, ValueError) as e:
        log.warning("creative brief: AI pass unavailable (%s); using the stored analysis only", e)
    needs = [{k: strip_echo(n.get(k))[:200] for k in ("feature", "functional_benefit", "emotional_benefit", "problem_solved")}
             for n in (llm.get("customer_needs") or []) if isinstance(n, dict) and n.get("feature")][:5]
    if not needs:  # deterministic fallback: pair features with benefits
        bens = list(p.benefits or [])
        needs = [{"feature": f, "functional_benefit": bens[i] if i < len(bens) else "", "emotional_benefit": "",
                  "problem_solved": strategy["pain_points"][i] if i < len(strategy["pain_points"]) else ""}
                 for i, f in enumerate(list(p.features or [])[:4])]
    first_angle = next((a.get("hook") for a in strategy["marketing_angles"] if a.get("hook")), "")
    brief.update({
        "hook": (strip_echo(llm.get("hook")) or first_angle or (strategy["usps"][0] if strategy["usps"] else ""))[:300],
        "creative_concept": (strip_echo(llm.get("creative_concept")) or strategy["creative_strategy"].get("lifestyle") or "")[:300],
        "target": (strip_echo(llm.get("target")) or (strategy["personas"][0]["name"] if strategy["personas"] else ""))[:200],
        "customer_needs": needs, "ai_pass": bool(llm),
    })
    r = ProductResearch(product_id=p.id, kind="brief", result=brief, provider=provider_used or "shelfcraft",
                        model=model_used or "assembled from stored analysis (non-AI)", inputs=sources)
    db.add(r)
    db.flush()
    return r


def get_brief(db: Session, product_id: str, *, provider: str | None = None, rebuild: bool = False) -> ProductResearch:
    """Reuse the latest brief while none of its sources changed; otherwise build a new one."""
    p = db.get(Product, product_id)
    if p is None:
        raise ValueError("product not found")
    cur = _latest(db, product_id, ("brief",))
    if cur and not rebuild and (cur.inputs or {}) == _sources(db, p):
        return cur
    return build_brief(db, product_id, provider)


def brief_out(r: ProductResearch | None, db: Session | None = None) -> dict[str, Any] | None:
    if r is None:
        return None
    stale = None
    if db is not None:
        p = db.get(Product, r.product_id)
        stale = bool(p) and (r.inputs or {}) != _sources(db, p)  # type: ignore[arg-type]
    return {"id": r.id, "created_at": r.created_at, "provider": r.provider, "model": r.model, "sources": r.inputs,
            "stale": stale, **{k: (r.result or {}).get(k) for k in ("hook", "creative_concept", "target", "customer_needs",
                                                                     "reviews", "strategy", "ai_pass")}}


def brief_text(brief: dict[str, Any]) -> str:
    s = brief.get("strategy") or {}
    lines = [f"Hook: {brief.get('hook') or '(none)'}", f"Creative concept: {brief.get('creative_concept') or '(none)'}",
             f"Target: {brief.get('target') or '(general shoppers)'}"]
    if s.get("positioning"):
        lines.append(f"Positioning: {s['positioning']}")
    for label, key in (("USPs", "usps"), ("Pain points", "pain_points"), ("Objections", "objections")):
        if s.get(key):
            lines.append(f"{label}: {'; '.join(map(str, s[key]))}")
    if s.get("personas"):
        lines.append("Personas: " + "; ".join(f"{x.get('name')} (pains: {', '.join(map(str, x.get('pain_points') or []))})"
                                              for x in s["personas"]))
    cs = s.get("creative_strategy") or {}
    if cs:
        lines.append("Deep Strategy image ideas: " + "; ".join(f"{k}: {v if isinstance(v, str) else ', '.join(map(str, v))}"
                                                            for k, v in cs.items() if v))
    for n in brief.get("customer_needs") or []:
        lines.append(f"Need: {n.get('feature')} -> {n.get('functional_benefit')} -> {n.get('emotional_benefit')} "
                     f"(solves: {n.get('problem_solved')})")
    rv = brief.get("reviews") or {}
    if rv.get("love"):
        lines.append(f"Customers love: {', '.join(rv['love'])}")
    if rv.get("hate"):
        lines.append(f"Customers complain about: {', '.join(rv['hate'])}")
    specs = (brief.get("product") or {}).get("specifications") or {}
    if specs:
        lines.append("Specs: " + "; ".join(f"{k}: {v}" for k, v in specs.items()))
    return "\n".join(lines)


# ---------------------------------------------------------------- plan
def _words(s: str, n: int) -> str:
    return " ".join(str(s or "").split()[:n])


def focus_points(brief: dict[str, Any]) -> list[tuple[str, str]]:
    """Every distinct strategy point of the brief, as (source, text)."""
    s = brief.get("strategy") or {}
    needs = brief.get("customer_needs") or []
    rv = brief.get("reviews") or {}
    specs = (brief.get("product") or {}).get("specifications") or {}
    pts: list[tuple[str, str]] = []
    if brief.get("hook"):
        pts.append(("hook", str(brief["hook"])))
    pts += [("pain_point", str(x)) for x in s.get("pain_points") or []]
    pts += [("pain_point", n["problem_solved"]) for n in needs if n.get("problem_solved")]
    pts += [("usp", str(x)) for x in s.get("usps") or []]
    pts += [("benefit", f"{n['feature']}: {n.get('functional_benefit') or n.get('emotional_benefit')}") for n in needs
            if n.get("feature") and (n.get("functional_benefit") or n.get("emotional_benefit"))]
    pts += [("persona", f"{x.get('name')}: {', '.join(map(str, x.get('pain_points') or []))}") for x in s.get("personas") or [] if x.get("name")]
    pts += [("review", f"customers love: {x}") for x in rv.get("love") or []]
    if specs:
        pts.append(("spec", "; ".join(f"{k}: {v}" for k, v in specs.items())))
    seen: set[str] = set()
    return [(k, t) for k, t in pts if t.strip() and not (t.lower() in seen or seen.add(t.lower()))]


def assign_focus(order: list[str], brief: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """Give each slot its own strategy point (preferred kind first, never reusing a point while unused ones remain)."""
    pts = focus_points(brief)
    used: set[int] = set()
    out: dict[str, tuple[str, str]] = {}
    for slot in order:
        prefs = SLOT_FOCUS.get(slot, ("benefit", "usp", "hook"))
        if slot == "main_white":
            out[slot] = ("hook", "Clear, compliant main image: the product itself on white")
            continue
        pick = next((i for kind in prefs for i, (k, _t) in enumerate(pts) if k == kind and i not in used), None)
        if pick is None and slot != "dimensions":
            pick = next((i for i in range(len(pts)) if i not in used), None)
        if pick is None:
            out[slot] = ("spec", "product specifications") if slot == "dimensions" else \
                ("hook", str(brief.get("hook") or "the product's main benefit"))
            continue
        used.add(pick)
        out[slot] = pts[pick]
    return out


_STOP = {"with", "your", "from", "that", "this", "for", "and", "the", "more", "most", "very", "into", "skin"}


def grounded(text: str, corpus: str) -> bool:
    """True when a callout shares a meaningful word or a number with the facts/brief (drops invented claims)."""
    toks = [t for t in re.findall(r"[a-z0-9]+", text.lower()) if (len(t) >= 4 or any(c.isdigit() for c in t)) and t not in _STOP]
    return not toks or any(re.search(r"(?<![a-z0-9])" + re.escape(t[:6] if len(t) > 6 else t), corpus) for t in toks)


def strip_product_name(text: str, name: str) -> str:
    """Drop runs of 2+ consecutive words of the product name: the real photo is composited, so the background
    model must not be asked to paint the product (it would add a second, invented one)."""
    name_words = {w.lower() for w in re.findall(r"[\w-]+", name or "") if len(w) > 1}
    words = (text or "").split()
    keep = [True] * len(words)
    i = 0
    while i < len(words):
        j = i
        while j < len(words) and re.sub(r"[^\w-]", "", words[j]).lower() in name_words:
            j += 1
        if j - i >= 2:
            keep[i:j] = [False] * (j - i)
        i = max(j, i + 1)
    out = " ".join(w for w, k in zip(words, keep) if k)
    return re.sub(r"\s+([,.:;])", r"\1", re.sub(r"\s{2,}", " ", out)).strip(" ,.:;")


def finalize_slot(slot: str, d: dict[str, Any], rules: dict[str, Any], *, source: str, provider: str | None = None,
                  model: str | None = None) -> dict[str, Any]:
    """Enforce the slot's shape and the brand limits, and flag banned words. Used for AI, fallback and user edits."""
    r = clean_rules(rules)
    has_text = SLOT_GUIDE.get(slot, ("", True))[1]
    callouts = d.get("callouts") or []
    if isinstance(callouts, str):
        callouts = [c for c in callouts.replace(";", "\n").split("\n") if c.strip()]
    out = {
        "slot": slot,
        "purpose": str(d.get("purpose") or SLOT_GUIDE.get(slot, ("",))[0])[:300],
        "concept": _words(d.get("concept") or "", 40),
        "headline": _words(d.get("headline") or "", r["headline_max_words"]) if has_text else "",
        "callouts": [_words(c, 6) for c in callouts if str(c).strip()][: r["callouts_max"]] if has_text else [],
        "people": bool(d.get("people")) and slot not in ("main_white", "dimensions", "detail"),
        "strategy_source": d.get("strategy_source") if d.get("strategy_source") in SOURCES else ("spec" if slot == "dimensions" else "benefit"),
        "strategy_note": str(d.get("strategy_note") or "")[:300],
        "source": source, "provider": provider, "model": model,
    }
    hits = banned_hits(" ".join([out["headline"], *out["callouts"], out["concept"]]), r)
    out["flags"] = [f"uses banned word “{h}”" for h in hits]
    return out


def _deterministic(slot: str, focus: tuple[str, str], brief: dict[str, Any]) -> dict[str, Any] | None:
    """Slots that need no AI: the white main image and the dimensions graphic (measurements come from the specs)."""
    if slot == "main_white":
        return {"purpose": SLOT_GUIDE[slot][0], "concept": "", "strategy_source": "hook", "strategy_note": focus[1]}
    if slot == "dimensions":
        specs = (brief.get("product") or {}).get("specifications") or {}
        meas = [f"{k}: {v}" for k, v in specs.items() if re.search(r"\d", str(v))]
        return {"purpose": SLOT_GUIDE[slot][0], "headline": "Size & dimensions", "callouts": meas[:4],
                "strategy_source": "spec", "strategy_note": "; ".join(meas[:4]) or "product specifications"}
    return None


def fallback_slot(slot: str, brief: dict[str, Any], copy: dict[str, Any],
                  focus: tuple[str, str] | None = None) -> dict[str, Any]:
    """No AI: reuse the listing copy's image strategy for the slot, else derive it from the brief."""
    out = _fallback_core(slot, brief, copy)
    if focus and slot != "dimensions":
        out = {**out, "strategy_source": focus[0], "strategy_note": focus[1]}
    return out


def _fallback_core(slot: str, brief: dict[str, Any], copy: dict[str, Any]) -> dict[str, Any]:
    old = next((s for s in copy.get("image_strategy") or [] if isinstance(s, dict) and s.get("slot") == slot), None)
    if old:
        return {"concept": old.get("concept"), "headline": old.get("headline"), "callouts": old.get("callouts") or [],
                "strategy_note": "from the listing copy's image strategy"}
    s = brief.get("strategy") or {}
    needs = brief.get("customer_needs") or []
    feats = [n.get("feature") for n in needs if n.get("feature")] or list((brief.get("product") or {}).get("features") or [])
    specs = (brief.get("product") or {}).get("specifications") or {}
    if slot == "dimensions":
        return {"headline": "Size & dimensions", "callouts": [f"{k}: {v}" for k, v in list(specs.items())[:4]],
                "strategy_source": "spec", "strategy_note": "product specifications"}
    if slot == "comparison":
        pain = (s.get("pain_points") or [""])[0]
        return {"headline": copy.get("headline") or "Why it's different", "callouts": feats[:4],
                "strategy_source": "pain_point", "strategy_note": pain}
    if slot in ("infographic_features", "detail"):
        return {"headline": copy.get("headline") or "", "callouts": feats[:4], "strategy_source": "usp",
                "strategy_note": "; ".join(map(str, (s.get("usps") or [])[:2]))}
    cs = s.get("creative_strategy") or {}
    emo = next((n.get("emotional_benefit") for n in needs if n.get("emotional_benefit")), "")
    return {"concept": cs.get("lifestyle") if slot.startswith("lifestyle") else "", "headline": emo or brief.get("hook") or copy.get("headline") or "",
            "callouts": [], "strategy_source": "hook", "strategy_note": brief.get("hook") or ""}


def plan_slot(slot: str, *, brief: dict[str, Any], rules: dict[str, Any], copy: dict[str, Any], marketplace: str,
              earlier: list[dict[str, Any]], focus: tuple[str, str] | None = None, product_name: str = "",
              provider: str | None = None) -> dict[str, Any]:
    mk = MARKETPLACES.get(marketplace, MARKETPLACES["amazon"])
    purpose, has_text = SLOT_GUIDE.get(slot, (f"Listing image: {slot}", True))
    focus = focus or ("benefit", str(brief.get("hook") or ""))
    if (det := _deterministic(slot, focus, brief)) is not None:
        return finalize_slot(slot, det, rules, source="auto")
    r = clean_rules(rules)
    done = "\n".join(f"- {e['slot']}: {e.get('headline') or '(no text)'}" for e in earlier) or "(none yet)"
    rt = rules_text(rules)
    text_rule = (f"headline at most {r['headline_max_words']} words; at most {r['callouts_max']} callouts of at most 5 words, "
                 "each taken from the facts or the brief (no new claims)." if has_text else
                 "This image has NO text: headline must be \"\" and callouts [].")
    prompt = (f"Plan ONE image of a {mk['label']} listing image set.\n"
              f"Slot: {slot}. Purpose: {purpose}\n"
              f"This image must prove this point: {focus[1]}\n\nCreative brief:\n{brief_text(brief)}\n\n"
              + (f"Brand rules:\n{rt}\n\n" if rt else "")
              + f"Listing title: {copy.get('title') or '(not written yet)'}\n"
              + f"\nHeadlines already used (don't repeat them):\n{done}\n\n"
              "The real product photo is placed into the scene afterwards, so the concept describes only the setting, "
              "surface, light and allowed props. " + text_rule + " Never use banned words.\n"
              f"{SLOT_FIELDS}\nReturn JSON exactly in this shape:\n{SLOT_SCHEMA}")
    corpus = (brief_text(brief) + " " + " ".join(map(str, copy.get("bullets") or [])) + " " + str(copy.get("title") or "")).lower()
    try:
        res = fm.generate_text(TextRequest(prompt=prompt, system=SYSTEM, json_mode=True, temperature=0.5, max_tokens=400),
                               purpose=f"image_plan_{slot}", preferred=provider)
        data = res.json()
        # Only accept an answer shaped like a slot plan (a reply in another shape must not pass as one).
        if isinstance(data, dict) and (data.get("concept") or data.get("purpose")) and (data.get("headline") or not has_text):
            concept = strip_product_name(strip_echo(data.get("concept")), product_name)
            headline = strip_echo(data.get("headline"))
            if headline and headline.lower() in {str(e.get("headline") or "").lower() for e in earlier}:
                headline = focus[1].split(":")[0]  # repeated headline -> say this image's own point instead
            callouts = data.get("callouts") if isinstance(data.get("callouts"), list) else []
            kept = [c for c in callouts if grounded(str(c), corpus)]
            d = {**data, "purpose": strip_echo(data.get("purpose")),
                 "concept": concept, "callouts": kept, "headline": headline,
                 "strategy_source": focus[0], "strategy_note": focus[1]}
            out = finalize_slot(slot, d, rules, source="ai", provider=res.provider, model=res.model)
            if len(kept) < len(callouts):
                log.info("image plan %s: dropped %d callout(s) not found in the facts", slot, len(callouts) - len(kept))
            if not out["flags"]:
                return out
            log.info("image plan %s: AI used banned words %s; using fallback", slot, out["flags"])
    except (NoProviderAvailable, ValueError) as e:
        log.warning("image plan %s: AI unavailable (%s); using fallback", slot, e)
    return finalize_slot(slot, fallback_slot(slot, brief, copy, focus), rules, source="fallback")


def build_plan(db: Session, project_id: str, *, provider: str | None = None, rebuild_brief: bool = False,
               slots: list[str] | None = None, progress: Callable[[float, str], None] | None = None) -> dict[str, Any]:
    tick = progress or (lambda *_a: None)
    proj = db.get(Project, project_id)
    if proj is None:
        raise ValueError("listing project was deleted")
    if not proj.product_id:
        raise ValueError("this listing has no product")
    data = dict(proj.data or {})
    marketplace = data.get("marketplace", "amazon")
    tick(0.05, "Preparing the creative brief")
    br = get_brief(db, proj.product_id, provider=provider, rebuild=rebuild_brief)
    db.commit()  # release SQLite's write lock before the slow per-slot AI calls
    brand = db.get(Brand, proj.brand_id) if proj.brand_id else None
    rules = (brand.rules if brand else None) or {}
    copy = data.get("copy") or {}
    order = slots or MARKETPLACES.get(marketplace, MARKETPLACES["amazon"])["image_slots"]
    focus = assign_focus(list(order), br.result)
    product = db.get(Product, proj.product_id)
    planned: list[dict[str, Any]] = []
    for i, slot in enumerate(order):
        tick(0.1 + 0.85 * i / len(order), f"Planning image {i + 1} of {len(order)}: {slot}")
        planned.append(plan_slot(slot, brief=br.result, rules=rules, copy=copy, marketplace=marketplace, earlier=planned,
                                 focus=focus.get(slot), product_name=product.name if product else "", provider=provider))
    plan = {"slots": planned, "brief_id": br.id, "brand_rules": bool(rules_text(rules)),
            "created_at": datetime.now(UTC).isoformat(), "edited_by_user": False}
    proj = db.get(Project, project_id)
    data = dict(proj.data or {})  # type: ignore[union-attr]
    data["image_plan"] = plan
    proj.data = data  # type: ignore[union-attr]
    return plan


def save_plan_edits(db: Session, proj: Project, slots: list[dict[str, Any]]) -> dict[str, Any]:
    brand = db.get(Brand, proj.brand_id) if proj.brand_id else None
    rules = (brand.rules if brand else None) or {}
    data = dict(proj.data or {})
    old = {s["slot"]: s for s in (data.get("image_plan") or {}).get("slots") or []}
    fixed = []
    for s in slots:
        slot = str(s.get("slot") or "")
        if slot not in SLOT_GUIDE:
            raise ValueError(f"unknown image slot {slot!r}")
        prev = old.get(slot, {})
        changed = any((s.get(k) or None) != (prev.get(k) or None) for k in EDITABLE)
        fixed.append(finalize_slot(slot, s, rules, source="user" if changed or not prev else prev.get("source", "user"),
                                   provider=prev.get("provider"), model=prev.get("model")))
    plan = {**(data.get("image_plan") or {}), "slots": fixed, "edited_by_user": True}
    data["image_plan"] = plan
    proj.data = data
    return plan
