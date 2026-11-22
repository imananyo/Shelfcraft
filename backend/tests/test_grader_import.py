"""Listing grader: import a public Amazon page (or a saved page) into the grader, then grade it."""
from __future__ import annotations

from app.services import marketplace_scrape as ms
from tests.conftest import make_png

ASIN = "B0TEST1234"


def amazon_page(aplus: bool = True, description: bool = False) -> str:
    imgs = ",".join(f'{{"hiRes":"https://m.media-amazon.com/images/I/img{i}.jpg"}}' for i in range(3))
    bullets = "".join(f'<li><span class="a-list-item">BENEFIT {i}: detail number {i} for the shopper</span></li>' for i in range(5))
    return (f'<html><head><link rel="canonical" href="https://www.amazon.in/dp/{ASIN}"></head><body>'
            f'<input id="ASIN" value="{ASIN}"><span id="productTitle"> Summit Steel Bottle 750 ml Insulated </span>'
            '<a id="bylineInfo">Visit the Summit Store</a>'
            f'<div id="feature-bullets"><ul>{bullets}</ul></div>'
            + ('<div id="productDescription"><p>A bottle for long trails.</p></div>' if description else "")
            + '<div id="aplus_feature_div">' + ('<div class="aplus-v2"><img src="x.jpg"></div>' if aplus else "") + "</div>"
            f'<script>var data = {{"colorImages": [{imgs}]}};</script>'
            '<span id="corePrice_feature_div"><span class="a-offscreen">₹1,299.00</span></span>'
            + "x" * 300 + "</body></html>")


def _patch(monkeypatch, html: str, calls: list[str] | None = None):
    def fetch(url):
        if calls is not None:
            calls.append(url)
        return html

    monkeypatch.setattr(ms, "fetch_page", fetch)
    monkeypatch.setattr(ms, "download_image", lambda url: make_png(1200, 1200))


def test_import_amazon_url_fills_grader_and_skips_hidden_sections(client, monkeypatch):
    calls: list[str] = []
    _patch(monkeypatch, amazon_page(aplus=True), calls)
    r = client.post("/api/grader/import", json={"url": f"https://www.amazon.in/Summit-Bottle/dp/{ASIN}/ref=sr_1_6?th=1"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert calls == [f"https://www.amazon.in/dp/{ASIN}"]  # cleaned link, right marketplace
    assert d["id"] == ASIN and d["title"] == "Summit Steel Bottle 750 ml Insulated" and len(d["bullets"]) == 5
    assert d["brand"] == "Summit" and d["has_aplus"] is True and len(d["assets"]) == 3 and d["price"] == 1299.0
    assert set(d["skip"]) == {"search_terms", "description"}  # no description because A+ replaces it
    assert "grader" in d["assets"][0]["tags"]
    g = client.post("/api/grader", json={"title": d["title"], "bullets": d["bullets"], "description": d["description"],
                                         "brand": d["brand"], "asset_ids": [a["id"] for a in d["assets"]],
                                         "has_aplus": d["has_aplus"], "skip": d["skip"]}).json()
    keys = [s["key"] for s in g["sections"]]
    assert "search_terms" not in keys and "description" not in keys and {s["key"] for s in g["skipped"]} == {"search_terms", "description"}
    assert next(s for s in g["sections"] if s["key"] == "aplus")["score"] == 100
    assert not any(c["section"] in ("search_terms", "description") for c in g["top_fixes"])


def test_import_without_aplus_grades_description_and_bare_asin_uses_country(client, monkeypatch):
    calls: list[str] = []
    _patch(monkeypatch, amazon_page(aplus=False, description=True), calls)
    d = client.post("/api/grader/import", json={"url": ASIN.lower(), "country": "UK"}).json()
    assert calls == [f"https://www.amazon.co.uk/dp/{ASIN}"]
    assert d["has_aplus"] is False and d["description"] == "A bottle for long trails." and list(d["skip"]) == ["search_terms"]


def test_import_rejects_non_amazon_links_and_reports_blocks(client, monkeypatch):
    assert client.post("/api/grader/import", json={"url": "https://example.com/x"}).status_code == 422
    assert client.post("/api/grader/import", json={"url": "https://www.amazon.com/s?k=bottle"}).status_code == 422

    def blocked(url):
        raise ms.ScrapeError("the marketplace showed a CAPTCHA / bot check instead of the product page")

    monkeypatch.setattr(ms, "fetch_page", blocked)
    r = client.post("/api/grader/import", json={"url": f"https://www.amazon.com/dp/{ASIN}"})
    assert r.status_code == 422 and r.json()["detail"]["blocked"] is True and "CAPTCHA" in r.json()["detail"]["message"]


def test_import_from_saved_page_source(client, monkeypatch):
    monkeypatch.setattr(ms, "download_image", lambda url: make_png(800, 800))
    d = client.post("/api/grader/import", json={"html": amazon_page(aplus=False)}).json()
    assert d["id"] == ASIN and d["url"] == f"https://www.amazon.in/dp/{ASIN}" and len(d["assets"]) == 3


def test_detect_aplus_ignores_empty_containers():
    assert ms.detect_aplus('<div id="aplus_feature_div"></div><div id="aplusBrandStory_feature_div"> </div>') is False
    assert ms.detect_aplus('<div id="aplus"><div class="aplus-module"><img src="a.jpg"></div></div>') is True


def test_bullets_from_newer_product_facts_layout():
    html = ('<span id="productTitle">Bell Keychain</span><div id="productFactsDesktopExpander"><ul>'
            '<li><span class="a-list-item">GUARDIAN BELL: engraved eagle design</span></li>'
            '<li><span class="a-list-item">EVIL EYE CHARM: blue glass bead</span></li></ul></div>'
            '<div id="pqv-feature-bullets"><ul><li><span class="a-list-item">GUARDIAN BELL: engraved eagle design</span></li></ul></div>')
    assert ms.parse_amazon(html)["features"] == ["GUARDIAN BELL: engraved eagle design", "EVIL EYE CHARM: blue glass bead"]
