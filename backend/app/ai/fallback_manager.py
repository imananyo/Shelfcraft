"""Free-only provider selection with retries, backoff, rate-limit handling and a circuit breaker.

Order: requested provider → user's fallback order → local providers. A provider is only ever
tried if it is enabled, configured, free-eligible (local or verified-free), its circuit is
closed, and it is not inside a rate-limit window. Every call is recorded (without secrets).
"""
from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any, TypeVar

from app.ai.base import (
    ImageRequest,
    ImageResult,
    NoProviderAvailable,
    ProviderAuthError,
    ProviderError,
    ProviderNotConfigured,
    ProviderRateLimited,
    ProviderRefused,
    TextRequest,
    TextResult,
)
from app.ai.provider_registry import PROVIDERS, get_provider, is_free_eligible, paid_allowed, runtime_config
from app.ai.usage_tracker import record_attempt
from app.db.models import ProviderConfig, UserSettings
from app.db.session import session_scope

log = logging.getLogger("shelfcraft.ai")

MAX_RETRIES = 2  # per provider, only for retryable (network/5xx) errors → 3 attempts max
CIRCUIT_THRESHOLD = 3
CIRCUIT_COOLDOWN = timedelta(minutes=5)
DEFAULT_RATE_LIMIT_COOLDOWN = timedelta(seconds=60)

T = TypeVar("T", TextResult, ImageResult)


def _aware(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


def candidate_order(kind: str, preferred: str | None) -> list[str]:
    with session_scope() as db:
        settings = db.query(UserSettings).first()
        default = None
        order: list[str] = []
        if settings:
            default = settings.default_text_provider if kind == "text" else settings.default_image_provider
            order = list(settings.fallback_order or [])
    names: list[str] = []
    for n in [preferred, default, *order]:
        if n and n in PROVIDERS and n not in names:
            names.append(n)
    for n, p in PROVIDERS.items():  # local providers are always the last resort
        if p.info.local and n not in names:
            names.append(n)
    # Paid providers only ever run when the user picked them explicitly for this request.
    return [n for n in names if kind in PROVIDERS[n].info.kinds and (not PROVIDERS[n].info.paid or n == preferred)]


def _skip_reason(name: str, explicit: bool = False) -> str | None:
    p = get_provider(name)
    if p.info.paid:
        if not explicit:
            return "paid provider — only used when you select it explicitly"
        with session_scope() as db:
            if not paid_allowed(db):
                return "paid provider — turn on \"Allow paid providers\" in Settings first"
    elif not is_free_eligible(p):
        return "not verified free — blocked by free-only policy"
    now = datetime.now(timezone.utc)
    with session_scope() as db:
        cfg = runtime_config(db, name)
        row = db.get(ProviderConfig, name)
        if not cfg.enabled:
            return "disabled"
        if not p.is_configured(cfg):
            return "not configured"
        if row:
            if (rl := _aware(row.rate_limited_until)) and rl > now:
                return f"rate limited until {rl:%H:%M:%S} UTC"
            if (co := _aware(row.circuit_open_until)) and co > now:
                return f"temporarily unavailable (circuit open until {co:%H:%M:%S} UTC)"
    return None


def _mark(name: str, *, ok: bool, error: ProviderError | None = None) -> None:
    now = datetime.now(timezone.utc)
    with session_scope() as db:
        row = db.get(ProviderConfig, name)
        if row is None:
            return
        if ok:
            row.last_success_at, row.consecutive_failures = now, 0
            row.circuit_open_until = None
            return
        row.last_failure_at = now
        row.last_error = (error.message if error else "unknown error")[:1000]
        if isinstance(error, ProviderRateLimited):
            cooldown = timedelta(seconds=error.retry_after_s) if error.retry_after_s else DEFAULT_RATE_LIMIT_COOLDOWN
            row.rate_limited_until = now + min(cooldown, timedelta(hours=1))
            return
        if isinstance(error, (ProviderNotConfigured, ProviderAuthError, ProviderRefused)):
            return  # configuration problems don't trip the breaker; user must fix them
        row.consecutive_failures = (row.consecutive_failures or 0) + 1
        if row.consecutive_failures >= CIRCUIT_THRESHOLD:
            row.circuit_open_until = now + CIRCUIT_COOLDOWN


def _run(kind: str, purpose: str, preferred: str | None, call: Callable[[str], T],
         prompt: str, params: dict[str, Any], strict: bool = False) -> T:
    attempts: list[dict[str, Any]] = []
    names = [preferred] if (strict and preferred) else candidate_order(kind, preferred)
    for name in names:
        reason = _skip_reason(name, explicit=(name == preferred))
        if reason:
            attempts.append({"provider": name, "error": reason, "skipped": True})
            continue
        for attempt in range(MAX_RETRIES + 1):
            t0 = time.perf_counter()
            try:
                result = call(name)
            except ProviderError as e:
                latency = int((time.perf_counter() - t0) * 1000)
                log.warning("%s %s via %s failed (attempt %d): %s", kind, purpose, name, attempt + 1, e.message)
                record_attempt(kind=kind, purpose=purpose, provider=name, model=None, ok=False,
                               latency_ms=latency, error=e.message, prompt=prompt, params=params)
                if e.retryable and attempt < MAX_RETRIES:
                    time.sleep(min(8.0, (2 ** attempt) + random.uniform(0, 0.5)))
                    continue
                _mark(name, ok=False, error=e)
                attempts.append({"provider": name, "error": e.message})
                break
            else:
                _mark(name, ok=True)
                record_attempt(kind=kind, purpose=purpose, provider=name, model=result.model, ok=True,
                               latency_ms=result.latency_ms, prompt=prompt, params=params,
                               input_tokens=getattr(result, "input_tokens", None),
                               output_tokens=getattr(result, "output_tokens", None),
                               providers_tried=[a["provider"] for a in attempts] + [name])
                return result
    raise NoProviderAvailable(kind, attempts)


def generate_text(req: TextRequest, *, purpose: str, preferred: str | None = None,
                  strict: bool = False) -> TextResult:
    def call(name: str) -> TextResult:
        p = get_provider(name)
        with session_scope() as db:
            cfg = runtime_config(db, name)
        # Only pass an explicit model to the provider it was chosen for.
        r = TextRequest(**{**req.__dict__, "model": req.model if name == preferred else None})
        if r.images and not p.info.vision:
            r.images = []
        return p.generate_text(r, cfg)

    return _run("text", purpose, preferred, call, req.prompt, {"json": req.json_mode}, strict)


def generate_image(req: ImageRequest, *, purpose: str, preferred: str | None = None,
                   strict: bool = False) -> ImageResult:
    def call(name: str) -> ImageResult:
        p = get_provider(name)
        with session_scope() as db:
            cfg = runtime_config(db, name)
        r = ImageRequest(**{**req.__dict__, "model": req.model if name == preferred else None})
        return p.generate_image(r, cfg)

    return _run("image", purpose, preferred, call, req.prompt,
                {"w": req.width, "h": req.height, "steps": req.steps}, strict)


def text_available() -> bool:
    return any(_skip_reason(n) is None for n in candidate_order("text", None))


def image_available() -> bool:
    return any(_skip_reason(n) is None for n in candidate_order("image", None))
