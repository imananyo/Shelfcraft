"""Import a product by Amazon ASIN, Walmart item ID or product URL (network calls are stubbed)."""
import pytest

from app.routers.integrations import classify_source


@pytest.mark.parametrize("kind,value,expected", [
    ("asin", "b08n5wrwnw", ("asin", "B08N5WRWNW")),
    ("asin", "https://www.amazon.com/Some-Thing/dp/B08N5WRWNW/ref=sr_1_1?x=1", ("asin", "B08N5WRWNW")),
    ("walmart", "5129928603", ("walmart", "5129928603")),
    ("walmart", "https://www.walmart.com/ip/Cool-Bottle-32oz/5129928603?athbdg=L1600", ("walmart", "5129928603")),
    ("url", "https://www.amazon.co.uk/gp/product/B0ABCDEF12", ("asin", "B0ABCDEF12")),
    ("url", "walmart.com/ip/123456789", ("walmart", "123456789")),
    ("url", "https://shop.example.com/products/x", ("url", "https://shop.example.com/products/x")),
])
def test_classify(kind, value, expected):
    assert classify_source(kind, value) == expected


AMAZON_HTML = """<html><body>
<span id="productTitle"> Trailhead 32oz Insulated Bottle </span>
<a id="bylineInfo">Visit the Trailhead Store</a>
<div id="wayfinding-breadcrumbs_feature_div"><a>Sports</a><a>Water Bottles</a></div>
<div id="corePriceDisplay_desktop_feature_div"><span class="a-offscreen">$24.99</span></div>
<div id="feature-bullets"><ul><li><span class="a-list-item">Keeps drinks cold 24 hours</span></li>
<li><span class="a-list-item">Leakproof lid</span></li></ul></div>
<div id="productDescription"><p>A tough bottle for long hikes.</p></div>
<table id="productDetails_techSpec_section_1"><tr><th>Capacity</th><td>32 Fluid Ounces</td></tr></table>
<script>var data = {"hiRes":"https://m.media-amazon.com/images/I/abc.jpg"};</script>
</body></html>"""

WALMART_HTML = """<html><body><script id="__NEXT_DATA__" type="application/json">""" + __import__("json").dumps({
    "props": {"pageProps": {"initialData": {"data": {
        "product": {"name": "Trailhead Bottle 32oz", "brand": "Trailhead",
                    "priceInfo": {"currentPrice": {"price": 19.97, "currencyUnit": "USD"}},
                    "imageInfo": {"allImages": [{"url": "https://i5.walmartimages.com/a.jpg"}]},
                    "category": {"path": [{"name": "Sports"}, {"name": "Water Bottles"}]},
                    "shortDescription": "<p>Stay hydrated.</p>"},
        "idml": {"longDescription": "<ul><li>BPA free</li><li>Dishwasher safe</li></ul>",
                 "specifications": [{"name": "Color", "value": "Teal"}]}}}}}}) + """</script></body></html>"""


def test_parse_amazon():
    from app.services.marketplace_scrape import parse_amazon
    d = parse_amazon(AMAZON_HTML)
    assert d["name"] == "Trailhead 32oz Insulated Bottle" and d["brand"] == "Trailhead"
    assert d["features"] == ["Keeps drinks cold 24 hours", "Leakproof lid"] and d["price"] == 24.99
    assert d["category"] == "Water Bottles" and d["specifications"]["Capacity"] == "32 Fluid Ounces"
    assert d["images"] == ["https://m.media-amazon.com/images/I/abc.jpg"]


def test_parse_walmart():
    from app.services.marketplace_scrape import parse_walmart
    d = parse_walmart(WALMART_HTML)
    assert d["name"] == "Trailhead Bottle 32oz" and d["price"] == 19.97 and d["category"] == "Water Bottles"
    assert d["features"] == ["BPA free", "Dishwasher safe"] and d["specifications"] == {"Color": "Teal"}


def _no_images(monkeypatch):
    from app.services import marketplace_scrape as ms
    monkeypatch.setattr(ms, "download_image", lambda url: None)


def test_import_asin_scrapes_page(client, monkeypatch):
    from app.services import marketplace_scrape as ms
    seen = {}
    monkeypatch.setattr(ms, "fetch_page", lambda url: seen.setdefault("url", url) and AMAZON_HTML)
    _no_images(monkeypatch)
    r = client.post("/api/products/import-source", json={"kind": "asin", "value": "https://www.amazon.de/dp/B08N5WRWNW", "country": "DE"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert seen["url"] == "https://www.amazon.de/dp/B08N5WRWNW"
    assert body["asin"] == "B08N5WRWNW" and body["name"] == "Trailhead 32oz Insulated Bottle"
    assert body["features"][0] == "Keeps drinks cold 24 hours" and body["import"]["complete"] is True


def test_import_walmart_scrapes_page(client, monkeypatch):
    from app.services import marketplace_scrape as ms
    monkeypatch.setattr(ms, "fetch_page", lambda url: WALMART_HTML)
    _no_images(monkeypatch)
    r = client.post("/api/products/import-source", json={"kind": "walmart", "value": "5129928603"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Trailhead Bottle 32oz" and body["price"] == 19.97
    assert body["specifications"]["Walmart item ID"] == "5129928603" and body["specifications"]["Color"] == "Teal"


def test_import_blocked_falls_back_to_id(client, monkeypatch):
    from app.services import marketplace_scrape as ms

    def blocked(url):
        raise ms.ScrapeError("the marketplace showed a CAPTCHA / bot check instead of the product page")
    monkeypatch.setattr(ms, "fetch_page", blocked)
    r = client.post("/api/products/import-source", json={"kind": "walmart", "value": "5129928603"})
    assert r.status_code == 201 and r.json()["import"]["complete"] is False
    assert "CAPTCHA" in r.json()["import"]["note"]


def test_import_rejects_bad_ids(client):
    assert client.post("/api/products/import-source", json={"kind": "asin", "value": "nope"}).status_code == 422
    assert client.post("/api/products/import-source", json={"kind": "walmart", "value": "abc"}).status_code == 422
    assert client.post("/api/products/import-source", json={"kind": "url", "value": "http://127.0.0.1/x"}).status_code == 422


def test_share_link_public_gallery(client):
    import io

    from PIL import Image

    proj = client.post("/api/projects", json={"name": "Share me", "kind": "design"})
    assert proj.status_code == 201, proj.text
    pid = proj.json()["id"]
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), "blue").save(buf, "PNG")
    up = client.post("/api/assets", files={"files": ("a.png", buf.getvalue(), "image/png")})
    assert up.status_code == 201, up.text
    aid = up.json()[0]["id"]
    from app.db.models import Asset
    from app.db.session import session_scope
    with session_scope() as db:
        db.get(Asset, aid).project_id = pid
    s = client.post(f"/api/projects/{pid}/share").json()
    assert s["enabled"] and s["url"].startswith("/share/")
    view = client.get(f"/api{s['url']}").json()
    assert view["title"] == "Share me"
    assert [i["id"] for i in view["items"]] == [aid]
    assert client.get(view["items"][0]["url"]).status_code == 200
    assert client.get("/api/share/not-a-real-token-123456").status_code == 404
    client.delete(f"/api/projects/{pid}/share")
    assert client.get(f"/api{s['url']}").status_code == 404


def test_svg_export_has_editable_layers():
    from app.imaging.svg_export import document_to_svg

    svg = document_to_svg({"width": 400, "height": 300, "background": "#fff", "layers": [
        {"type": "rect", "name": "Badge", "x": 10, "y": 10, "width": 100, "height": 40, "fill": "#ff0000", "cornerRadius": 8},
        {"type": "text", "name": "Headline", "x": 20, "y": 80, "width": 300, "height": 40, "text": "Keeps cold 24h & more",
         "fontSize": 28, "fontFamily": "Inter", "fill": "#111111", "align": "center", "rotation": 5},
        {"type": "line", "x": 0, "y": 0, "points": [0, 0, 50, 50], "stroke": "#000"},
    ]})
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert 'id="Badge"' in svg and 'id="Headline"' in svg and "Keeps cold 24h &amp;" in svg and "<tspan" in svg
    assert "rotate(5" in svg and "<polyline" in svg and 'text-anchor="middle"' in svg
    import xml.dom.minidom
    xml.dom.minidom.parseString(svg)  # well-formed


def test_aplus_convert_to_mobile_keeps_edits(client):
    a = client.post("/api/aplus", json={"name": "Bottle A+", "tier": "premium", "modules": ["brand_story", "lifestyle"]}).json()
    doc_id = a["modules"][0]["document_id"]
    d = client.get(f"/api/documents/{doc_id}").json()
    doc = d["document"]
    for ly in doc["layers"]:
        if ly.get("name") == "Headline":
            ly["text"] = "Made in Colorado since 2009"
    r = client.put(f"/api/documents/{doc_id}", json={"document": doc, "base_version": d["version"]})
    assert r.status_code == 200, r.text
    m = client.post(f"/api/aplus/{a['id']}/convert-mobile")
    assert m.status_code == 201, m.text
    mob = m.json()
    assert mob["tier"] == "mobile" and len(mob["modules"]) == 2
    md = client.get(f"/api/documents/{mob['modules'][0]['document_id']}").json()["document"]
    assert md["width"] == 600
    assert any(ly.get("text") == "Made in Colorado since 2009" for ly in md["layers"])
    assert client.post(f"/api/aplus/{mob['id']}/convert-mobile").status_code == 422


def test_keep_prompting_adds_jobs_to_same_session(client):
    r = client.post("/api/creative/generate", json={"creative_type": next(iter(client.get("/api/creative/options").json()["creative_types"])),
                                                   "count": 1})
    assert r.status_code == 202, r.text
    sid = r.json()["session_id"]
    m = client.post(f"/api/creative/sessions/{sid}/more", json={"prompt": "on a marble counter", "count": 2})
    assert m.status_code == 202, m.text
    assert m.json()["session_id"] == sid and len(m.json()["jobs"]) == 2
    s = client.get(f"/api/creative/sessions/{sid}").json()
    assert len(s["jobs"]) >= 3 and s["params"]["follow_ups"] == ["on a marble counter"]


def test_listing_add_more_and_remove_visuals(client):
    import io

    from PIL import Image

    from app.db.models import Asset, Project
    from app.db.session import session_scope

    buf = io.BytesIO()
    Image.new("RGB", (16, 16), "green").save(buf, "PNG")
    ids = [client.post("/api/assets", files={"files": (f"v{i}.png", buf.getvalue(), "image/png")}).json()[0]["id"] for i in range(2)]
    with session_scope() as db:
        p = Project(kind="listing", name="Session test", data={"marketplace": "amazon", "images": [
            {"slot": "main", "asset_ids": [ids[0]]}, {"slot": "lifestyle", "asset_ids": [ids[1]]}]})
        db.add(p)
        db.flush()
        pid = p.id
        for aid in ids:
            db.get(Asset, aid).project_id = pid
    jobs = client.post(f"/api/listings/{pid}/images/more", json={"prompt": "on a beach", "count": 2})
    assert jobs.status_code == 202 and len(jobs.json()) == 2 and jobs.json()[0]["type"] == "listing_more_images"
    assert client.post(f"/api/listings/{pid}/images/more", json={"creative_type": "nope"}).status_code == 422
    r = client.post(f"/api/listings/{pid}/images/remove", json={"asset_ids": [ids[0]]})
    assert r.status_code == 200, r.text
    assert [i["asset_id"] for i in r.json()["images"]] == [ids[1]]


def test_notification_preferences_mute_success(client):
    from app.db.models import Notification
    from app.db.session import session_scope
    from app.jobs.handlers import _notify

    gd = client.get("/api/settings").json()["generation_defaults"]
    client.patch("/api/settings", json={"generation_defaults": {**gd, "notify": {"success": False, "warning": True}}})
    try:
        with session_scope() as db:
            before = db.query(Notification).count()
            _notify(db, "muted success")
            _notify(db, "kept warning", level="warning")
            _notify(db, "kept error", level="error")
            db.flush()
            assert db.query(Notification).count() == before + 2
    finally:
        client.patch("/api/settings", json={"generation_defaults": gd})


def test_public_api_and_mcp_parity_tools(client, monkeypatch):
    import asyncio

    import mcp_server
    from app.services import marketplace_scrape as ms

    monkeypatch.setattr(ms, "fetch_page", lambda url: WALMART_HTML)
    monkeypatch.setattr(ms, "download_image", lambda url: None)
    k = client.post("/api/api-keys", json={"name": "parity"}).json()
    h = {"Authorization": f"Bearer {k['key']}"}
    p = client.post("/v1/products/import", headers=h, json={"kind": "walmart", "value": "5129928603"})
    assert p.status_code == 201, p.text
    a = client.post("/v1/aplus", headers=h, json={"name": "API A+", "product_id": p.json()["id"], "modules": ["brand_story"]})
    assert a.status_code == 201, a.text
    m = client.post(f"/v1/aplus/{a.json()['id']}/convert-mobile", headers=h)
    assert m.status_code == 201 and m.json()["tier"] == "mobile"
    assert client.post(f"/v1/projects/{a.json()['id']}/share", headers=h).json()["url"].startswith("/share/")
    assert client.patch(f"/v1/projects/{a.json()['id']}", headers=h, json={"name": "Renamed"}).json()["name"] == "Renamed"
    assert client.get("/v1/recent-work", headers=h).status_code == 200
    assert "by_provider" in client.get("/v1/usage", headers=h).json()
    names = {t.name for t in asyncio.run(mcp_server.server.list_tools())}
    assert {"import_product", "add_visuals", "download_listing_visuals", "list_recent_work", "rename_recent_work", "share_link",
            "create_aplus", "convert_a_plus_desktop_to_mobile", "get_usage", "create_listing_visuals"} <= names
    client.delete(f"/api/api-keys/{k['id']}")
