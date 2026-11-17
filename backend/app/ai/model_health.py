"""Shared handling for hosted models that get retired or overloaded.

Free tiers change their model line-up all the time (Nov 2026: Gemini dropped gemini-2.5-flash for new users, Groq
removed llama-3.3-70b-versatile, OpenRouter moved llama-3.3-70b-instruct off the free tier). A model saved in
Settings must not break every request when that happens:
- providers default to AUTO, i.e. the best suitable model the key can currently use;
- a "model not found / decommissioned / no longer free" answer marks the model retired, switches to the automatic
  choice, retries once, and resets the saved setting so the error does not repeat;
- an overloaded model (HTTP 503) falls through to the next-best model once.
"""
from __future__ import annotations

import hashlib
import logging
import re
import time

log = logging.getLogger("shelfcraft.models")

AUTO = "auto"
CACHE_TTL = 12 * 3600
_retired: dict[str, set[str]] = {}
_auto_cache: dict[tuple[str, str], tuple[str, float]] = {}

_GONE = ("model_not_found", "does not exist", "decommissioned", "no longer available", "no longer supported",
         "unavailable for free", "not_found", "not found", "deprecated")


def fingerprint(key: str | None) -> str:
    return hashlib.sha256((key or "").encode()).hexdigest()[:16]


def model_gone(message: str) -> bool:
    """True when a 400/404 answer says the requested model can't be used any more."""
    m = message.lower()
    return bool(re.search(r"http (400|404)", m)) and any(s in m for s in _GONE)


def is_retired(provider: str, model: str) -> bool:
    return model in _retired.get(provider, set())


def mark_retired(provider: str, model: str) -> None:
    _retired.setdefault(provider, set()).add(model)
    for k in [k for k, v in _auto_cache.items() if k[0] == provider and v[0] == model]:
        _auto_cache.pop(k, None)


def cached(provider: str, key: str | None) -> str | None:
    hit = _auto_cache.get((provider, fingerprint(key)))
    if hit and time.time() - hit[1] < CACHE_TTL and not is_retired(provider, hit[0]):
        return hit[0]
    return None


def remember(provider: str, key: str | None, model: str) -> None:
    _auto_cache[(provider, fingerprint(key))] = (model, time.time())


def reset() -> None:  # tests
    _retired.clear()
    _auto_cache.clear()


def forget_saved_model(provider: str, model: str) -> None:
    """A retired model saved in Settings would fail on every call: reset the setting to automatic and clear the
    error it caused."""
    try:
        from app.db.models import ProviderConfig
        from app.db.session import session_scope

        with session_scope() as db:
            row = db.get(ProviderConfig, provider)
            if row is not None and row.text_model == model:
                row.text_model = None
                if row.last_error and (model in row.last_error or model_gone(row.last_error)):
                    row.last_error = None
    except Exception:  # noqa: BLE001 - never let bookkeeping break a generation
        log.exception("could not reset the retired %s model setting", provider)


# ---------------------------------------------------------------- generic ranking for OpenAI-compatible catalogs
NON_CHAT = re.compile(r"whisper|tts|orpheus|guard|safeguard|embed|rerank|moderation|transcri|audio|speech|playai|"
                      r"image|vision-only|ocr", re.I)
WEAKER = re.compile(r"preview|exp\b|experimental|code|coder|omni|-vl\b|vl:|vision|nano|mini|tiny|small|lite|"
                    r"lightning|instant|1\.7b|-3b|\b[0-9]b\b|allam", re.I)


def size_b(name: str) -> float:
    """Largest '<n>b' parameter count in a model id (MoE total), e.g. 'gpt-oss-120b' → 120, 'x-550b-a55b' → 550."""
    sizes = [float(x) for x in re.findall(r"(?<![a-z])(\d+(?:\.\d+)?)b(?![a-z0-9])", name.lower())]
    return max(sizes) if sizes else 0.0


def rank_models(models: list[str], provider: str) -> list[str]:
    """Chat models ordered best-first: no speech/guard/embedding models, full models before preview/mini/code ones,
    then larger before smaller."""
    usable = [m for m in models if not NON_CHAT.search(m) and not is_retired(provider, m)]
    return sorted(usable, key=lambda m: (bool(WEAKER.search(m)), -size_b(m), m))
