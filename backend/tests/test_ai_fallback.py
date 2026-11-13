"""Provider fallback: order, free-only enforcement, retries, rate limits, circuit breaker."""
from __future__ import annotations

from typing import Any

import pytest

from app.ai import fallback_manager as fm
from app.ai import provider_registry as reg
from app.ai.base import (
    NoProviderAvailable,
    Provider,
    ProviderInfo,
    ProviderRateLimited,
    ProviderRuntimeConfig,
    ProviderUnavailable,
    TextRequest,
    TextResult,
)
from app.db.models import ProviderConfig, UsageRecord
from app.db.session import session_scope


class Fake(Provider):
    def __init__(self, name: str, *, local: bool = False, free: bool = True, behavior: list[Any] | None = None) -> None:
        self.info = ProviderInfo(name=name, label=name, kinds=("text",), local=local, free_tier_verified=free,
                                 verified_on="2026-11-13", source_url="", limits_note="", privacy_note="",
                                 requires_key=False, default_text_model=f"{name}-model")
        self.behavior = behavior or ["ok"]
        self.calls = 0

    def generate_text(self, req: TextRequest, cfg: ProviderRuntimeConfig) -> TextResult:
        b = self.behavior[min(self.calls, len(self.behavior) - 1)]
        self.calls += 1
        if isinstance(b, Exception):
            raise b
        return TextResult(text='{"ok": true}', provider=self.info.name, model=f"{self.info.name}-model")


@pytest.fixture
def fakes(client, monkeypatch):
    """Replace the registry with controllable fakes (client fixture ensures DB is bootstrapped)."""
    providers: dict[str, Fake] = {}

    def install(*items: Fake) -> dict[str, Fake]:
        providers.clear()
        providers.update({p.info.name: p for p in items})
        monkeypatch.setattr(reg, "PROVIDERS", providers)
        monkeypatch.setattr(fm, "PROVIDERS", providers)
        monkeypatch.setattr(fm.time, "sleep", lambda s: None)
        with session_scope() as db:
            for name in providers:
                row = db.get(ProviderConfig, name) or ProviderConfig(name=name)
                row.enabled, row.consecutive_failures = True, 0
                row.circuit_open_until = row.rate_limited_until = None
                db.add(row)
            from app.db.models import UserSettings

            s = db.query(UserSettings).first()
            s.default_text_provider = list(providers)[0]
            s.fallback_order = list(providers)
        return providers

    return install


def test_primary_used_when_healthy(fakes):
    p = fakes(Fake("alpha"), Fake("beta"))
    r = fm.generate_text(TextRequest(prompt="hi"), purpose="t")
    assert r.provider == "alpha" and p["beta"].calls == 0


def test_falls_back_on_rate_limit_and_records_window(fakes):
    p = fakes(Fake("alpha", behavior=[ProviderRateLimited("alpha", "429", retry_after_s=120)]), Fake("beta"))
    r = fm.generate_text(TextRequest(prompt="hi"), purpose="t")
    assert r.provider == "beta"
    assert p["alpha"].calls == 1  # rate limits are not retried against the same provider
    with session_scope() as db:
        assert db.get(ProviderConfig, "alpha").rate_limited_until is not None
    # While rate-limited, alpha is skipped entirely.
    fm.generate_text(TextRequest(prompt="again"), purpose="t")
    assert p["alpha"].calls == 1


def test_bounded_retries_then_circuit_opens(fakes):
    flaky = Fake("alpha", behavior=[ProviderUnavailable("alpha", "503")])
    p = fakes(flaky, Fake("beta"))
    for _ in range(3):
        assert fm.generate_text(TextRequest(prompt="x"), purpose="t").provider == "beta"
    assert p["alpha"].calls == 9  # 3 attempts per call (1 + MAX_RETRIES), never unbounded
    with session_scope() as db:
        assert db.get(ProviderConfig, "alpha").circuit_open_until is not None
    fm.generate_text(TextRequest(prompt="x"), purpose="t")
    assert p["alpha"].calls == 9  # circuit open → skipped


def test_unverified_provider_never_called(fakes):
    paid = Fake("paidco", free=False)
    p = fakes(paid, Fake("local", local=True))
    r = fm.generate_text(TextRequest(prompt="x"), purpose="t", preferred="paidco")
    assert r.provider == "local" and p["paidco"].calls == 0


def test_strict_mode_does_not_fall_back(fakes):
    fakes(Fake("alpha", behavior=[ProviderUnavailable("alpha", "down")]), Fake("beta"))
    with pytest.raises(NoProviderAvailable):
        fm.generate_text(TextRequest(prompt="x"), purpose="t", preferred="alpha", strict=True)


def test_all_down_raises_clear_error_and_usage_logged(fakes):
    fakes(Fake("alpha", behavior=[ProviderUnavailable("alpha", "down")]),
          Fake("beta", behavior=[ProviderUnavailable("beta", "down")]))
    with pytest.raises(NoProviderAvailable) as ei:
        fm.generate_text(TextRequest(prompt="x"), purpose="t")
    assert "alpha" in str(ei.value) and "beta" in str(ei.value)
    with session_scope() as db:
        assert db.query(UsageRecord).filter(UsageRecord.success.is_(False)).count() >= 6


def test_openrouter_rejects_paid_models_before_network():
    from app.ai.base import ProviderRefused
    from app.ai.openrouter_provider import OpenRouterProvider

    p = OpenRouterProvider()
    assert p.allowed_model("meta-llama/llama-3.3-70b-instruct:free")
    assert not p.allowed_model("openai/gpt-4o")
    cfg = ProviderRuntimeConfig(enabled=True, api_key="k", extra={}, text_model=None, image_model=None)
    with pytest.raises(ProviderRefused):
        p.generate_text(TextRequest(prompt="x", model="anthropic/claude-x"), cfg)


def test_gemini_blocks_image_models():
    from app.ai.gemini_provider import GeminiProvider

    g = GeminiProvider()
    assert g.allowed_model("gemini-2.5-flash")
    assert not g.allowed_model("gemini-2.5-flash-image")
    assert not g.allowed_model("imagen-4.0-generate")


def test_every_registered_provider_is_free_or_blocked():
    from app.ai.provider_registry import PROVIDERS, is_free_eligible

    for name, p in PROVIDERS.items():
        assert p.info.verified_on, name
        if not is_free_eligible(p):
            assert name == "mistral"  # documented: unverified → can never be enabled


def test_json_parsing_is_tolerant():
    from app.ai.base import parse_json_loose

    assert parse_json_loose('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_loose('Sure! Here it is: {"a": [1,2]} hope that helps') == {"a": [1, 2]}
    with pytest.raises(ValueError):
        parse_json_loose("no json here")
