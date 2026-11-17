"""Retired / overloaded models on OpenAI-compatible free providers (Groq, OpenRouter), Nov 2026."""
import pytest

from app.ai import model_health as mh
from app.ai import openai_compat as oc
from app.ai.base import ProviderBadResponse, ProviderNotConfigured, ProviderRuntimeConfig, ProviderUnavailable, TextRequest

GROQ = ["allam-2-7b", "canopylabs/orpheus-arabic-saudi", "canopylabs/orpheus-v1-english", "meta-llama/llama-prompt-guard-2-22m",
        "meta-llama/llama-prompt-guard-2-86m", "openai/gpt-oss-120b", "openai/gpt-oss-20b", "openai/gpt-oss-safeguard-20b",
        "qwen/qwen3.8-27b", "whisper-large-v3", "whisper-large-v3-turbo"]
OPENROUTER = ["baidu/ernie-5.5-flash-preview:free", "cohere/north-mini-code:free", "dots-studio/dots-3-note-preview:free",
              "google/gemma-4-26b-a4b-it:free", "google/gemma-4-31b-it:free", "inclusionai/ling-3.2-flash:free",
              "liquid/lfm-3-1.7b:free", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
              "nvidia/nemotron-3-ultra-550b-a55b:free", "nvidia/nemotron-3.5-lightning:free", "nvidia/nemotron-3.5-super-vl:free"]
GROQ_GONE = ('HTTP 404: {"error":{"message":"The model `llama-3.3-70b-versatile` does not exist or you do not have access '
             'to it.","type":"invalid_request_error","code":"model_not_found"}}')
OR_GONE = 'HTTP 404: {"error":{"message":"This model is unavailable for free. The paid version is available."}}'


def cfg(text_model=None):
    return ProviderRuntimeConfig(api_key="k", enabled=True, extra={}, text_model=text_model, image_model=None)


@pytest.fixture(autouse=True)
def _reset():
    mh.reset()
    yield
    mh.reset()


def test_ranking_picks_real_chat_models():
    assert mh.rank_models(GROQ, "groq")[:3] == ["openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b"]
    ranked = mh.rank_models(OPENROUTER, "openrouter")
    assert ranked[0] == "nvidia/nemotron-3-ultra-550b-a55b:free" and ranked[1] == "google/gemma-4-31b-it:free"
    assert not any("whisper" in m or "guard" in m or "orpheus" in m for m in mh.rank_models(GROQ, "groq"))
    assert mh.model_gone(GROQ_GONE) and mh.model_gone(OR_GONE)
    assert mh.model_gone('HTTP 400: {"error":{"code":"model_decommissioned","message":"has been decommissioned"}}')
    assert not mh.model_gone("HTTP 400: invalid json") and not mh.model_gone("HTTP 503")


def _fake(monkeypatch, provider, models, *, gone=(), busy=(), gone_msg=GROQ_GONE):
    sent = []

    def fake(prov, method, url, **kw):
        if url.endswith("/models"):
            return {"data": [{"id": m, "pricing": {"prompt": "0"}} for m in models]}
        body = kw["json_body"]
        sent.append(body)
        if body["model"] in gone:
            raise ProviderBadResponse(prov, gone_msg)
        if body["model"] in busy:
            raise ProviderUnavailable(prov, "HTTP 503")
        return {"choices": [{"message": {"content": f"ok from {body['model']}"}}], "usage": {}}
    monkeypatch.setattr(oc, "request_json", fake)
    import app.ai.openrouter_provider as orp
    monkeypatch.setattr(orp, "request_json", fake)
    return sent


def test_groq_default_is_auto_with_low_reasoning(monkeypatch):
    from app.ai.groq_provider import GroqProvider
    sent = _fake(monkeypatch, "groq", GROQ)
    r = GroqProvider().generate_text(TextRequest(prompt="x"), cfg())
    assert r.model == "openai/gpt-oss-120b" and sent[-1]["reasoning_effort"] == "low"


def test_groq_retired_saved_model_switches_and_heals(client, monkeypatch):
    from app.ai.groq_provider import GroqProvider
    from app.db.models import ProviderConfig
    from app.db.session import session_scope
    _fake(monkeypatch, "groq", GROQ + ["llama-3.3-70b-versatile"], gone={"llama-3.3-70b-versatile"})
    with session_scope() as db:
        row = db.get(ProviderConfig, "groq")
        row.text_model, row.last_error = "llama-3.3-70b-versatile", GROQ_GONE
    r = GroqProvider().generate_text(TextRequest(prompt="x"), cfg("llama-3.3-70b-versatile"))
    assert r.model == "openai/gpt-oss-120b"
    with session_scope() as db:
        row = db.get(ProviderConfig, "groq")
        assert row.text_model is None and row.last_error is None


def test_openrouter_never_free_anymore_switches_to_another_free_model(monkeypatch):
    from app.ai.openrouter_provider import OpenRouterProvider
    _fake(monkeypatch, "openrouter", OPENROUTER, gone={"meta-llama/llama-3.3-70b-instruct:free"}, gone_msg=OR_GONE)
    r = OpenRouterProvider().generate_text(TextRequest(prompt="x"), cfg("meta-llama/llama-3.3-70b-instruct:free"))
    assert r.model.endswith(":free") and r.model == "nvidia/nemotron-3-ultra-550b-a55b:free"


def test_overloaded_model_falls_through_to_next(monkeypatch):
    from app.ai.openrouter_provider import OpenRouterProvider
    _fake(monkeypatch, "openrouter", OPENROUTER, busy={"nvidia/nemotron-3-ultra-550b-a55b:free"})
    r = OpenRouterProvider().generate_text(TextRequest(prompt="x"), cfg())
    assert r.model == "google/gemma-4-31b-it:free"


def test_retired_then_overloaded_keeps_going_and_clears_unnamed_error(client, monkeypatch):
    """Seen live: OpenRouter's 'unavailable for free' error doesn't name the model, and the first replacement was 503."""
    from app.ai.openrouter_provider import OpenRouterProvider
    from app.db.models import ProviderConfig
    from app.db.session import session_scope
    old = "meta-llama/llama-3.3-70b-instruct:free"
    sent = _fake(monkeypatch, "openrouter", OPENROUTER, gone={old}, gone_msg=OR_GONE,
                 busy={"nvidia/nemotron-3-ultra-550b-a55b:free"})
    with session_scope() as db:
        row = db.get(ProviderConfig, "openrouter")
        row.text_model, row.last_error = old, OR_GONE
    r = OpenRouterProvider().generate_text(TextRequest(prompt="x"), cfg(old))
    assert r.model == "google/gemma-4-31b-it:free"
    assert [b["model"] for b in sent] == [old, "nvidia/nemotron-3-ultra-550b-a55b:free", "google/gemma-4-31b-it:free"]
    with session_scope() as db:
        row = db.get(ProviderConfig, "openrouter")
        assert row.text_model is None and row.last_error is None


def test_gives_up_after_three_models(monkeypatch):
    from app.ai.openrouter_provider import OpenRouterProvider
    sent = _fake(monkeypatch, "openrouter", OPENROUTER, busy=set(OPENROUTER))
    with pytest.raises(ProviderUnavailable):
        OpenRouterProvider().generate_text(TextRequest(prompt="x"), cfg())
    assert len(sent) == 3  # protects the 50-requests/day free quota


def test_paid_provider_never_switches_models(monkeypatch):
    from app.ai.paid_providers import OpenAIProvider
    sent = _fake(monkeypatch, "openai", ["gpt-9", "gpt-5-mini"], gone={"gpt-5-mini"})
    p = OpenAIProvider()
    # Call the shared OpenAI-compatible path directly (OpenAIProvider adds its own paid-use checks on top).
    with pytest.raises(ProviderBadResponse):
        oc.OpenAICompatProvider.generate_text(p, TextRequest(prompt="x"), cfg("gpt-5-mini"))
    assert [b["model"] for b in sent] == ["gpt-5-mini"]  # no automatic retry with another paid model
    with pytest.raises(ProviderNotConfigured):
        oc.OpenAICompatProvider.generate_text(p, TextRequest(prompt="x"), cfg(mh.AUTO))
