"""Brand rules: the structured "how this brand may speak and look" used when planning images and writing copy.

Rules are drafted once by the text AI from the brand profile, then edited by the user. Everything is plain
lists/strings so a small local model can fill it reliably, and every consumer works when a field is empty.
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.ai import fallback_manager as fm
from app.ai.base import TextRequest
from app.db.models import Brand

LIST_FIELDS = ("safe_claims", "careful_claims", "banned_words", "props_allowed", "props_banned", "backgrounds",
               "fixed_elements", "variable_elements")
TEXT_FIELDS = ("photo_look", "layout_notes", "main_image_rules")
LIMITS = {"headline_max_words": (2, 12, 7), "callouts_max": (0, 6, 4)}

RULES_SCHEMA = """{
  "safe_claims": ["claims the facts fully support"],
  "careful_claims": ["claims that need qualifying wording"],
  "banned_words": ["words or claims never to use"],
  "photo_look": "lighting, contrast, colour temperature, mood",
  "layout_notes": "how text and product are arranged",
  "props_allowed": ["..."], "props_banned": ["..."], "backgrounds": ["..."],
  "fixed_elements": ["what stays the same in every image"],
  "variable_elements": ["what may change between images"],
  "main_image_rules": "rules for the marketplace main image"
}"""


def _clean_list(v: Any, n: int = 12) -> list[str]:
    if isinstance(v, str):
        v = re.split(r"[\n,;]", v)
    if not isinstance(v, list):
        return []
    seen: set[str] = set()
    out = []
    for x in v:
        s = str(x).strip(" •-*\t")[:120] if not isinstance(x, (dict, list)) else ""
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out[:n]


def clean_rules(raw: Any) -> dict[str, Any]:
    """Coerce AI or user input into the rules shape; unknown keys are dropped."""
    raw = raw if isinstance(raw, dict) else {}
    out: dict[str, Any] = {f: _clean_list(raw.get(f)) for f in LIST_FIELDS}
    # A thing can't be both allowed and banned (AI drafts sometimes list it twice): the stricter list wins.
    for allowed, banned in (("props_allowed", "props_banned"), ("safe_claims", "banned_words"), ("careful_claims", "banned_words")):
        ban = {x.lower() for x in out[banned]}
        out[allowed] = [x for x in out[allowed] if x.lower() not in ban]
    for f in TEXT_FIELDS:
        v = raw.get(f)
        out[f] = (" ".join(map(str, v)) if isinstance(v, list) else str(v or "")).strip()[:800]
    for f, (lo, hi, default) in LIMITS.items():
        try:
            out[f] = max(lo, min(hi, int(raw.get(f, default))))
        except (TypeError, ValueError):
            out[f] = default
    out["ai_drafted"] = bool(raw.get("ai_drafted"))
    return out


def is_empty(rules: dict[str, Any] | None) -> bool:
    r = rules or {}
    return not any(r.get(f) for f in LIST_FIELDS + TEXT_FIELDS)


def rules_text(rules: dict[str, Any] | None) -> str:
    """Compact text for prompts (empty string when the brand has no rules)."""
    if is_empty(rules):
        return ""
    r = clean_rules(rules)
    lines = []
    for label, f in (("Claims you may make", "safe_claims"), ("Claims that need careful wording", "careful_claims"),
                     ("Never use these words/claims", "banned_words"), ("Allowed props", "props_allowed"),
                     ("Banned props", "props_banned"), ("Backgrounds", "backgrounds"),
                     ("Keep the same in every image", "fixed_elements"), ("May vary between images", "variable_elements")):
        if r[f]:
            lines.append(f"{label}: {', '.join(r[f])}")
    for label, f in (("Photo look", "photo_look"), ("Layout", "layout_notes"), ("Main image rules", "main_image_rules")):
        if r[f]:
            lines.append(f"{label}: {r[f]}")
    lines.append(f"Image headlines at most {r['headline_max_words']} words; at most {r['callouts_max']} callouts.")
    return "\n".join(lines)


def banned_hits(text: str, rules: dict[str, Any] | None) -> list[str]:
    """Banned words/claims that appear in `text` (case-insensitive, whole words)."""
    low = (text or "").lower()
    hits = []
    for w in (rules or {}).get("banned_words") or []:
        w = str(w).strip().lower()
        if w and re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", low):
            hits.append(w)
    return hits


def draft_rules(db: Session, brand_id: str, provider: str | None = None) -> tuple[dict[str, Any], str, str]:
    """Ask the text AI for a first draft of the rules from the brand profile. Not saved: the user reviews it."""
    from app.routers.brands import brand_context

    b = db.get(Brand, brand_id)
    if b is None or b.deleted_at:
        raise ValueError("brand not found")
    ctx = brand_context(db, brand_id, include_rules=False)
    prompt = (f"Draft brand rules for product images and marketing claims.\n\n{ctx}\n\n"
              "Base every rule on the brand profile above; where it says nothing, give sensible, conservative "
              "e-commerce defaults (no medical, 'best', '#1' or guarantee claims unless the profile supports them). "
              "Keep each list to at most 8 short items.\n"
              f"Return JSON exactly in this shape:\n{RULES_SCHEMA}")
    res = fm.generate_text(TextRequest(prompt=prompt, system="You are a brand strategist. Respond with JSON only.",
                                       json_mode=True, temperature=0.3, max_tokens=1200),
                           purpose="brand_rules", preferred=provider)
    data = res.json()
    if not isinstance(data, dict):
        raise ValueError("model returned unexpected JSON")
    rules = clean_rules({**data, "ai_drafted": True})
    if is_empty(rules):
        raise ValueError("the model returned no usable rules — try again or add more detail to the brand profile")
    return rules, res.provider, res.model
