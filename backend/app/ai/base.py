"""Provider-independent AI interfaces.

Every adapter declares whether it is local, whether its recurring free access has been
verified (with a date and source), and which model IDs it will accept. The fallback
manager refuses to use anything that is not local or verified-free — paid calls are
structurally impossible rather than merely discouraged.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, ClassVar


# ---------------------------------------------------------------- errors
class ProviderError(Exception):
    """Base class. `retryable` tells the fallback manager whether to retry this provider."""

    retryable = False

    def __init__(self, provider: str, message: str) -> None:
        super().__init__(f"[{provider}] {message}")
        self.provider = provider
        self.message = message


class ProviderNotConfigured(ProviderError):
    pass


class ProviderAuthError(ProviderError):
    pass


class ProviderRateLimited(ProviderError):
    retryable = False  # move to next provider instead of hammering this one

    def __init__(self, provider: str, message: str, retry_after_s: float | None = None) -> None:
        super().__init__(provider, message)
        self.retry_after_s = retry_after_s


class ProviderUnavailable(ProviderError):
    retryable = True  # network errors, 5xx, timeouts


class ProviderBadResponse(ProviderError):
    retryable = True


class ProviderRefused(ProviderError):
    """Request rejected for policy / plan reasons (e.g. Cloudflare 403 on paid-only model)."""


class NoProviderAvailable(Exception):
    def __init__(self, kind: str, attempts: list[dict[str, Any]]) -> None:
        reasons = "; ".join(f"{a['provider']}: {a['error']}" for a in attempts) or "no provider is enabled"
        super().__init__(f"No {kind} provider could complete the request ({reasons})")
        self.kind = kind
        self.attempts = attempts


# ---------------------------------------------------------------- request/response
@dataclass
class TextRequest:
    prompt: str
    system: str | None = None
    temperature: float = 0.7
    max_tokens: int = 1500
    json_mode: bool = False
    images: list[bytes] = field(default_factory=list)  # for vision-capable providers
    model: str | None = None


@dataclass
class TextResult:
    text: str
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int = 0

    def json(self) -> Any:
        return parse_json_loose(self.text)


@dataclass
class ImageRequest:
    prompt: str
    negative_prompt: str | None = None
    width: int = 768
    height: int = 768
    steps: int | None = None
    seed: int | None = None
    model: str | None = None
    init_image: bytes | None = None  # img2img where supported
    strength: float = 0.6


@dataclass
class ImageResult:
    image_png: bytes
    provider: str
    model: str
    seed: int | None = None
    latency_ms: int = 0
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderInfo:
    """Static facts shown in Settings → Providers and FREE_RESOURCES.md."""

    name: str
    label: str
    kinds: tuple[str, ...]  # ("text",), ("image",), ("text","image")
    local: bool
    free_tier_verified: bool
    verified_on: str  # ISO date the free terms were checked
    source_url: str
    limits_note: str
    privacy_note: str
    license_note: str = ""
    requires_key: bool = True
    default_text_model: str | None = None
    default_image_model: str | None = None
    vision: bool = False
    paid: bool = False  # opt-in paid provider: never in the automatic fallback chain


@dataclass
class ProviderRuntimeConfig:
    """Resolved config for one call: DB row + env, secrets included (server-side only)."""

    enabled: bool
    api_key: str | None
    extra: dict[str, Any]
    text_model: str | None
    image_model: str | None


class Provider:
    info: ClassVar[ProviderInfo]

    def is_configured(self, cfg: ProviderRuntimeConfig) -> bool:
        return (not self.info.requires_key) or bool(cfg.api_key)

    def allowed_model(self, model: str) -> bool:
        """Override to restrict to free model IDs."""
        return True

    def generate_text(self, req: TextRequest, cfg: ProviderRuntimeConfig) -> TextResult:
        raise ProviderRefused(self.info.name, "text generation not supported")

    def generate_image(self, req: ImageRequest, cfg: ProviderRuntimeConfig) -> ImageResult:
        raise ProviderRefused(self.info.name, "image generation not supported")

    def list_models(self, cfg: ProviderRuntimeConfig) -> list[str]:
        return [m for m in (self.info.default_text_model, self.info.default_image_model) if m]

    def health(self, cfg: ProviderRuntimeConfig) -> dict[str, Any]:
        """Cheap connectivity check (no generation). Returns {"ok": bool, "detail": str}."""
        try:
            models = self.list_models(cfg)
            return {"ok": True, "detail": f"{len(models)} model(s) available", "models": models[:50]}
        except ProviderError as e:
            return {"ok": False, "detail": e.message}


# ---------------------------------------------------------------- helpers
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_json_loose(text: str) -> Any:
    """Parse model output that should be JSON but may be fenced or have chatter around it."""
    t = _FENCE.sub("", text.strip()).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    obj_first = t.find("{") != -1 and (t.find("[") == -1 or t.find("{") < t.find("["))
    for open_c, close_c in (("{", "}"), ("[", "]")):
        if open_c == "[" and obj_first:
            # The answer is an object; a nested list is not the answer — salvage the (cut-off) object instead.
            repaired = repair_truncated_json(t)
            if repaired is not None:
                return repaired
        start, end = t.find(open_c), t.rfind(close_c)
        if start != -1 and end > start:
            try:
                return json.loads(t[start : end + 1])
            except json.JSONDecodeError:
                continue
    repaired = repair_truncated_json(t)
    if repaired is not None:
        return repaired
    raise ValueError("model did not return valid JSON")


def repair_truncated_json(text: str) -> Any:
    """Salvage a JSON object that was cut off (output-token cap hit, e.g. when a small model loops).
    Cuts back to the last complete value and closes the open brackets. Returns None if nothing parses."""
    start = text.find("{")
    if start == -1:
        return None
    s = text[start:]
    stack: list[str] = []
    in_str = esc = False
    cuts: list[tuple[int, list[str]]] = []
    for i, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if stack:
                stack.pop()
            if not stack:
                try:
                    return json.loads(s[: i + 1])
                except json.JSONDecodeError:
                    return None
            cuts.append((i + 1, list(stack)))
        elif ch == ",":
            cuts.append((i, list(stack)))
    for idx, st in reversed(cuts[-400:]):
        try:
            out = json.loads(s[:idx] + "".join(reversed(st)))
        except json.JSONDecodeError:
            continue
        if isinstance(out, dict) and out:
            return out
    return None


def redact(text: str, secrets: list[str | None]) -> str:
    for s in secrets:
        if s and len(s) > 4:
            text = text.replace(s, "***")
    return text
