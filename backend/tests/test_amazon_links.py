"""Amazon link handling for the ASIN import: marketplace from the domain, share-link expansion."""
import httpx

from app.routers import integrations as integ


def test_country_from_link():
    f = integ.amazon_country_from_link
    assert f("https://www.amazon.in/dp/B0ABCDEFGH") == "IN"
    assert f("amazon.co.uk/x/dp/B0ABCDEFGH") == "UK"
    assert f("https://www.amazon.com.au/dp/B0ABCDEFGH") == "AU"
    assert f("https://www.amazon.com/dp/B0ABCDEFGH") == "US"
    assert f("B0ABCDEFGH") is None


def test_short_link_expanded_without_downloading_page(monkeypatch):
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(str(req.url))
        return httpx.Response(301, headers={"location": "https://www.amazon.in/dp/B0GR5R1NRC?ref=share"})

    real_client = httpx.Client
    monkeypatch.setattr(integ.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    url = integ.resolve_amazon_short_link("https://amzn.in/d/0c5inyi6")
    assert calls == ["https://amzn.in/d/0c5inyi6"]  # only the short link itself was requested
    assert integ.classify_source("asin", url) == ("asin", "B0GR5R1NRC")
    assert integ.amazon_country_from_link(url) == "IN"


def test_non_short_links_untouched():
    assert integ.resolve_amazon_short_link("B08N5WRWNW") == "B08N5WRWNW"
    assert integ.resolve_amazon_short_link("https://www.amazon.in/dp/B0GR5R1NRC") == "https://www.amazon.in/dp/B0GR5R1NRC"
