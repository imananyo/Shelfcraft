"""Opt-in paid providers (Nano Banana, OpenAI): never automatic, locked until the master switch is on."""
import base64
import io

from PIL import Image

from app.ai import fallback_manager as fm
from app.ai import paid_providers as pp
from app.ai.base import ImageRequest, ProviderRuntimeConfig


def _png() -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(b, "PNG")
    return b.getvalue()


def test_paid_never_in_automatic_order(client):
    for kind in ("text", "image"):
        assert not {"openai", "nano_banana"} & set(fm.candidate_order(kind, None))
    assert "openai" in fm.candidate_order("text", "openai")


def test_paid_locked_until_switch(client):
    r = client.patch("/api/providers/openai", json={"enabled": True})
    assert r.status_code == 422 and "Allow paid providers" in r.json()["detail"]
    assert "Allow paid" in fm._skip_reason("openai", explicit=True)
    assert "explicitly" in fm._skip_reason("openai", explicit=False)
    gd = client.get("/api/settings").json()["generation_defaults"]
    client.patch("/api/settings", json={"generation_defaults": {**gd, "allow_paid_providers": True}})
    try:
        r = client.patch("/api/providers/openai", json={"enabled": True, "api_key": "sk-test-not-real"})
        assert r.status_code == 200 and r.json()["paid"] is True
        assert fm._skip_reason("openai", explicit=True) is None
        assert fm._skip_reason("openai", explicit=False) is not None  # still never automatic
    finally:
        client.patch("/api/providers/openai", json={"enabled": False, "api_key": ""})
        client.patch("/api/settings", json={"generation_defaults": gd})


def test_nano_banana_parses_image(monkeypatch):
    sent = {}

    def fake(provider, method, url, **kw):
        sent.update(url=url, body=kw["json_body"])
        return {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "image/png", "data": base64.b64encode(_png()).decode()}}]}}]}
    monkeypatch.setattr(pp, "request_json", fake)
    cfg = ProviderRuntimeConfig(enabled=True, api_key="k", extra={}, text_model=None, image_model=None)
    r = pp.NanoBananaProvider().generate_image(ImageRequest(prompt="bottle on a rock", width=1600, height=900), cfg)
    assert r.image_png.startswith(b"\x89PNG") and r.model == "gemini-2.5-flash-image"
    assert "gemini-2.5-flash-image:generateContent" in sent["url"]
    assert sent["body"]["generationConfig"]["imageConfig"]["aspectRatio"] == "16:9"


def test_openai_image_parses(monkeypatch):
    monkeypatch.setattr(pp, "request_json", lambda *a, **k: {"data": [{"b64_json": base64.b64encode(_png()).decode()}]})
    cfg = ProviderRuntimeConfig(enabled=True, api_key="k", extra={}, text_model=None, image_model=None)
    r = pp.OpenAIProvider().generate_image(ImageRequest(prompt="x", width=1024, height=1024), cfg)
    assert r.model == "gpt-image-1" and r.meta["size"] == "1024x1024"
