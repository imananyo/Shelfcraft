"""Gemini model retirement: Google returns 404 "no longer available to new users" for retired models
(seen 2026-11-18 for gemini-2.5-flash). Shelfcraft must pick a model the key can use and heal saved settings."""
import pytest

from app.ai import gemini_provider as gp
from app.ai.base import ProviderBadResponse, ProviderRuntimeConfig, TextRequest

MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3.8-flash", "gemini-3.8-flash-lite",
          "gemini-3.9-flash-preview-11-2026", "gemini-3.8-pro", "gemini-flash-latest", "gemini-embedding-001",
          "gemini-3.8-flash-image"]
RETIRED_MSG = ('HTTP 404: {"error": {"code": 404, "message": "This model models/gemini-2.5-flash is no longer available '
               'to new users. Please update your code to use models/gemini-3.8-flash", "status": "NOT_FOUND"}}')


def cfg(text_model=None):
    return ProviderRuntimeConfig(api_key="k", enabled=True, extra={}, text_model=text_model, image_model=None)


@pytest.fixture(autouse=True)
def _clean_state():
    gp._auto_cache.clear()
    gp._retired.clear()
    yield
    gp._auto_cache.clear()
    gp._retired.clear()


def _fake_api(monkeypatch, retired=("gemini-2.5-flash",)):
    calls = []

    def fake(provider, method, url, **kw):
        calls.append(url)
        if url.endswith("/models?pageSize=200"):
            return {"models": [{"name": f"models/{m}", "supportedGenerationMethods":
                                ["embedContent"] if "embedding" in m else ["generateContent"]} for m in MODELS]}
        model = url.split("/models/")[1].split(":")[0]
        if model in retired:
            raise ProviderBadResponse("gemini", RETIRED_MSG.replace("gemini-2.5-flash", model))
        return {"candidates": [{"content": {"parts": [{"text": f"hi from {model}"}]}}], "usageMetadata": {}}
    monkeypatch.setattr(gp, "request_json", fake)
    return calls


def test_pick_model_prefers_newest_stable_flash():
    assert gp.pick_model(MODELS) == "gemini-3.8-flash"
    assert gp.pick_model(["gemini-flash-latest", "gemini-3.9-flash-preview-11-2026"]) == "gemini-flash-latest"
    assert gp.pick_model(["gemini-3.8-flash-lite", "gemini-2.5-flash-lite"]) == "gemini-3.8-flash-lite"
    assert gp.pick_model([]) is None


def test_default_is_automatic(monkeypatch):
    calls = _fake_api(monkeypatch)
    g = gp.GeminiProvider()
    r = g.generate_text(TextRequest(prompt="x"), cfg())
    assert r.model == "gemini-3.8-flash" and r.text == "hi from gemini-3.8-flash"
    g.generate_text(TextRequest(prompt="y"), cfg())
    assert sum(c.endswith("pageSize=200") for c in calls) == 1  # model list is cached


def test_retired_saved_model_switches_and_heals_setting(client, monkeypatch):
    from app.db.models import ProviderConfig
    from app.db.session import session_scope
    _fake_api(monkeypatch)
    with session_scope() as db:
        db.get(ProviderConfig, "gemini").text_model = "gemini-2.5-flash"
    g = gp.GeminiProvider()
    r = g.generate_text(TextRequest(prompt="x"), cfg(text_model="gemini-2.5-flash"))
    assert r.model == "gemini-3.8-flash"
    with session_scope() as db:
        assert db.get(ProviderConfig, "gemini").text_model is None  # saved retired model reset to automatic
    # Later calls skip the retired model even if something still asks for "auto".
    assert g.generate_text(TextRequest(prompt="z"), cfg()).model == "gemini-3.8-flash"


def test_overloaded_model_falls_back_to_lite(monkeypatch):
    """Seen live 2026-11-18: every Flash model answered 503 'high demand' while flash-lite-latest worked."""
    from app.ai.base import ProviderUnavailable

    def fake(provider, method, url, **kw):
        if url.endswith("pageSize=200"):
            return {"models": [{"name": f"models/{m}", "supportedGenerationMethods": ["generateContent"]} for m in
                               ("gemini-3.8-flash", "gemini-flash-lite-latest", "gemini-3.1-flash-lite")]}
        model = url.split("/models/")[1].split(":")[0]
        if "lite" not in model:
            raise ProviderUnavailable("gemini", "HTTP 503")
        return {"candidates": [{"content": {"parts": [{"text": "OK"}]}}]}
    monkeypatch.setattr(gp, "request_json", fake)
    r = gp.GeminiProvider().generate_text(TextRequest(prompt="x"), cfg())
    assert r.model == "gemini-flash-lite-latest" and r.text == "OK"


def test_other_errors_are_not_retried(monkeypatch):
    def fake(provider, method, url, **kw):
        if url.endswith("pageSize=200"):
            return {"models": [{"name": "models/gemini-3.8-flash", "supportedGenerationMethods": ["generateContent"]}]}
        raise ProviderBadResponse("gemini", "HTTP 400: invalid argument")
    monkeypatch.setattr(gp, "request_json", fake)
    with pytest.raises(ProviderBadResponse, match="HTTP 400"):
        gp.GeminiProvider().generate_text(TextRequest(prompt="x"), cfg())


def test_test_connection_reports_and_fixes_unavailable_saved_model(client, monkeypatch):
    from app.db.models import ProviderConfig
    from app.db.session import session_scope
    _fake_api(monkeypatch)
    with session_scope() as db:
        row = db.get(ProviderConfig, "gemini")
        row.api_key, row.text_model = "k", "gemini-2.0-flash"
    with session_scope() as db:
        db.get(ProviderConfig, "gemini").last_error = RETIRED_MSG  # the stale error the user saw in Settings
    r = client.post("/api/providers/gemini/test").json()
    assert r["ok"] and "isn't available" in r["detail"] and "gemini-3.8-flash" in r["detail"]
    assert client.get("/api/providers").json()  # status endpoint still works
    with session_scope() as db:
        row = db.get(ProviderConfig, "gemini")
        assert row.text_model is None and row.last_error is None  # a working test clears the old error
        row.api_key = None
