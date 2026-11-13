"""Core CRUD, uploads, assets, persistence, security checks."""
from __future__ import annotations

import io

from tests.conftest import make_png


def test_health_and_capabilities(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["checks"]["database"] == "ok"
    caps = client.get("/api/capabilities").json()
    assert caps["background_removal"] is True
    assert caps["text_ai"] is False  # no provider reachable in tests


def test_brand_crud_and_validation(client):
    r = client.post("/api/brands", json={"name": "Northwind", "colors": ["#0F766E", "#7c3aed"],
                                         "values": ["Honest", " "], "tone_of_voice": "Warm"})
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["colors"] == ["#0f766e", "#7c3aed"]
    assert b["values"] == ["Honest"]
    r = client.patch(f"/api/brands/{b['id']}", json={"tagline": "Made to last"})
    assert r.json()["tagline"] == "Made to last"
    bad = client.post("/api/brands", json={"name": "X", "colors": ["red"]})
    assert bad.status_code == 422 and "#RRGGBB" in bad.json()["detail"]
    assert client.get("/api/settings").json()["active_brand_id"] == b["id"]


def test_brand_logo_and_guideline_upload(client, png_bytes):
    b = client.post("/api/brands", json={"name": "LogoCo"}).json()
    r = client.post(f"/api/brands/{b['id']}/logo", files={"file": ("logo.png", png_bytes, "image/png")})
    assert r.status_code == 200 and r.json()["logo_url"]
    g = client.post(f"/api/brands/{b['id']}/guidelines",
                    files={"file": ("guide.md", b"# Voice\nAlways friendly.", "text/markdown")}, data={"title": "Voice"})
    assert g.status_code == 201 and "friendly" in g.json()["preview"]


def test_product_crud_images_variants_and_csv(client, png_bytes):
    r = client.post("/api/products", json={"name": "Trail Bottle", "sku": "TB-1", "category": "Outdoor",
                                           "features": ["Double-wall steel"], "price": 24.5,
                                           "variants": [{"name": "Red", "attributes": {"color": "red", "hex": "#cc0000"}}]})
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["variants"][0]["name"] == "Red"
    up = client.post(f"/api/products/{p['id']}/images",
                     files=[("files", ("a.png", png_bytes, "image/png")), ("files", ("b.png", make_png(color="#e76f51"), "image/png"))])
    assert up.status_code == 201 and up.json()["image_count"] == 2
    assert up.json()["images"][0]["role"] == "main"
    lst = client.get("/api/products", params={"q": "trail"}).json()
    assert any(i["id"] == p["id"] for i in lst["items"]) and "Outdoor" in lst["categories"]
    csv_text = client.get("/api/products/export.csv").text
    assert "Trail Bottle" in csv_text
    imp = client.post("/api/products/import.csv", files={"file": ("p.csv",
        "name,sku,price,features\nNew Lamp,LMP-1,19.99,Warm light|Dimmable\nTrail Bottle v2,TB-1,26,\n,,,\nBad,B1,abc,\n",
        "text/csv")}).json()
    assert imp["created"] == 1 and imp["updated"] == 1 and len(imp["errors"]) == 2


def test_upload_rejects_disguised_and_oversized_files(client):
    r = client.post("/api/assets", files={"files": ("evil.png", b"MZ\x90\x00 not really a png", "image/png")})
    assert r.status_code == 422 and r.json()["code"] == "upload_rejected"
    big = b"\x89PNG\r\n\x1a\n" + b"0" * (26 * 1024 * 1024)
    r = client.post("/api/assets", files={"files": ("big.png", big, "image/png")})
    assert r.status_code == 422


def test_path_traversal_blocked():
    import pytest

    from app.storage.local import StorageError, get_storage

    s = get_storage()
    for key in ("../secrets.txt", "uploads/../../x", "C:/Windows/win.ini", "/etc/passwd"):
        with pytest.raises(StorageError):
            s.path(key)


def test_asset_library_filters_favorites_folders_zip_convert(client, png_bytes):
    a = client.post("/api/assets", files={"files": ("photo.png", png_bytes, "image/png")}).json()[0]
    f = client.post("/api/assets/folders", json={"name": "Campaign"}).json()
    r = client.patch(f"/api/assets/{a['id']}", json={"favorite": True, "tags": ["hero"], "folder_id": f["id"]})
    assert r.json()["favorite"] is True
    assert client.get("/api/assets", params={"favorite": True, "tag": "hero"}).json()["total"] >= 1
    assert client.get("/api/assets", params={"folder_id": f["id"]}).json()["total"] == 1
    z = client.post("/api/assets/zip", json={"asset_ids": [a["id"]]})
    assert z.status_code == 200 and z.content[:2] == b"PK"
    c = client.get(f"/api/assets/{a['id']}/convert", params={"format": "jpeg", "width": 200})
    assert c.status_code == 200 and c.headers["x-export-width"] == "200" and c.content[:3] == b"\xff\xd8\xff"
    w = client.get(f"/api/assets/{a['id']}/convert", params={"format": "webp", "max_kb": 20})
    assert w.status_code == 200 and int(w.headers["x-export-bytes"]) <= 20 * 1024
    assert client.delete(f"/api/assets/{a['id']}").status_code == 204
    assert client.get(f"/api/assets/{a['id']}").status_code == 404


def test_provider_keys_never_exposed_and_paid_ineligible(client):
    r = client.patch("/api/providers/groq", json={"api_key": "gsk_SECRET_TEST_KEY_123"})
    assert r.status_code == 200
    body = client.get("/api/providers").text
    assert "gsk_SECRET_TEST_KEY_123" not in body
    groq = next(p for p in client.get("/api/providers").json() if p["name"] == "groq")
    assert groq["has_key"] is True
    m = client.patch("/api/providers/mistral", json={"enabled": True})
    assert m.status_code == 422 and "not verified" in m.json()["detail"]
    o = client.patch("/api/providers/openrouter", json={"text_model": "openai/gpt-4o"})
    assert o.status_code == 422 and "free allow-list" in o.json()["detail"]
    client.patch("/api/providers/groq", json={"api_key": ""})


def test_dashboard_and_search(client):
    client.post("/api/products", json={"name": "Searchable Mug"})
    d = client.get("/api/dashboard").json()
    assert d["counts"]["products"] >= 1 and len(d["checklist"]) == 3
    res = client.get("/api/search", params={"q": "Searchable"}).json()["results"]
    assert any(r["type"] == "product" for r in res)


def test_backup_creates_zip(client):
    r = client.post("/api/backups")
    assert r.status_code == 201
    name = r.json()["name"]
    dl = client.get(f"/api/backups/{name}")
    assert dl.status_code == 200 and dl.content[:2] == b"PK"
    assert client.get("/api/backups/..%2F..%2Fshelfcraft.db").status_code == 404


def test_validation_error_shape(client):
    r = client.post("/api/products", json={"name": ""})
    assert r.status_code == 422 and r.json()["code"] == "validation_error"


def test_png_helper_is_valid():
    from PIL import Image

    assert Image.open(io.BytesIO(make_png())).size == (400, 300)
