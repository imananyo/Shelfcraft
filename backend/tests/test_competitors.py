"""Top-performing listings: Best Sellers / search / product page parsing, merging, exact benchmark, AI analysis."""
import json
import re

import pytest

from app.ai.base import TextResult
from tests.conftest import run_pending_jobs


@pytest.fixture(autouse=True)
def _empty_job_queue(client):
    run_pending_jobs()  # start from an empty queue (other modules may leave jobs behind)


def _bs_item(rank, asin, title, price, stars, reviews):
    return f"""<div id="gridItemRoot"><div class="zg-grid-general-faceout"><span class="zg-bdg-text">#{rank}</span>
      <div data-asin="{asin}"><a class="a-link-normal" href="/Some-Slug/dp/{asin}/ref=zg_bs"><img alt="{title}" src="https://m.media-amazon.com/{asin}.jpg"></a>
      <a class="a-link-normal" href="/Some-Slug/dp/{asin}/ref=zg_bs"><div>{title}</div></a>
      <div class="a-icon-row"><a href="/product-reviews/{asin}"><i class="a-icon a-icon-star-small"><span class="a-icon-alt">{stars} out of 5 stars</span></i>
      <span class="a-size-small">{reviews}</span></a></div>
      <span class="a-size-base a-color-price"><span class="p13n-sc-price">${price}</span></span></div></div></div>"""


BESTSELLERS = ('<html><head><link rel="canonical" href="https://www.amazon.com/gp/bestsellers/sports/3226186011"></head><body>'
               '<h1>Best Sellers in Sports Water Bottles</h1>'
               + _bs_item(1, "B0AAAAAAA1", "HydroPeak Insulated Water Bottle with Straw Lid, 32 oz Stainless Steel", "24.95", "4.7", "52,301")
               + _bs_item(2, "B0AAAAAAA2", "Owala FreeSip Insulated Stainless Steel Water Bottle with Straw, 24 oz, Leak Proof", "27.99", "4.8", "1.2K")
               + _bs_item(3, "B0AAAAAAA3", "Simple Modern Kids Water Bottle with Straw Lid, Insulated Stainless Steel, 14 oz", "19.99", "4.6", "880")
               + _bs_item(4, "B08N5WRWNW", "Our Own Bottle", "21.00", "4.1", "12")  # the user's own listing
               + "</body></html>")


def _search_item(i, asin, title, price, sponsored=False, bought=None, badge=None):
    return f"""<div data-component-type="s-search-result" data-asin="{asin}" data-index="{i}">
      {'<span class="puis-sponsored-label-text">Sponsored</span>' if sponsored else ''}
      {f'<span class="a-badge-text">{badge}</span>' if badge else ''}
      <h2 aria-label="{'Sponsored Ad - ' if sponsored else ''}{title}"><span>{title}</span></h2>
      <span class="a-icon-alt">4.5 out of 5 stars</span><a href="/dp/{asin}#customerReviews"><span class="a-size-base s-underline-text">(3,410)</span></a>
      {f'<span class="a-size-base a-color-secondary">{bought}+ bought in past month</span>' if bought else ''}
      <span class="a-price"><span class="a-offscreen">${price}</span></span><img class="s-image" src="https://m.media-amazon.com/s{asin}.jpg"></div>"""


SEARCH = ('<html><body><input id="twotabsearchtextbox" value="insulated water bottle">'
          + _search_item(1, "B0AAAAAAA2", "Owala FreeSip Insulated Stainless Steel Water Bottle with Straw, 24 oz", "27.99", bought="10K", badge="Best Seller")
          + _search_item(2, "B0SPONSOR1", "Brand X Insulated Water Bottle Leak Proof Lid", "15.99", sponsored=True, bought="500")
          + _search_item(3, "B0AAAAAAA4", "Takeya Actives Insulated Stainless Steel Water Bottle with Spout Lid, 24 oz", "29.99")
          + "</body></html>")


def _review(rid, stars, text):
    return (f'<div data-hook="review" id="{rid}"><span class="a-profile-name">U{rid}</span><i data-hook="review-star-rating">'
            f'<span>{stars}.0 out of 5 stars</span></i><span data-hook="review-date">Reviewed in the United States on May 1, 2024</span>'
            f'<span data-hook="review-body"><span>{text}</span></span></div>')


PRODUCT_PAGE = ('<html><head><link rel="canonical" href="https://www.amazon.com/Owala/dp/B0AAAAAAA2"></head><body>'
                '<input type="hidden" id="ASIN" value="B0AAAAAAA2"><span id="productTitle">Owala FreeSip Insulated Stainless Steel Water Bottle with Straw, 24 oz</span>'
                '<a id="bylineInfo">Visit the Owala Store</a>'
                '<div id="feature-bullets"><ul><li><span class="a-list-item">2-IN-1 LID: sip through the straw or swig from the spout</span></li>'
                '<li><span class="a-list-item">LEAK PROOF: push-button lid locks closed</span></li></ul></div>'
                '<div id="detailBulletsWrapper_feature_div"><ul><li>Best Sellers Rank: #1,234 in Sports &amp; Outdoors (See Top 100) #2 in Sports Water Bottles</li></ul></div>'
                '<div id="aplus"><div class="aplus-module">A+ module</div></div>'
                '<script>var obj = {"hiRes":"https://m.media-amazon.com/1.jpg"},{"hiRes":"https://m.media-amazon.com/2.jpg"},'
                '{"hiRes":"https://m.media-amazon.com/3.jpg"}; var v = {"videos": [{"url":"x"}]};</script>'
                + _review("C1", 1, "The straw lid leaks in my bag.") + _review("C2", 2, "Lid leaks after a month.")
                + _review("C3", 5, "Keeps water cold all day.") + "</body></html>")

WALMART_SEARCH = ('<html><body><script id="__NEXT_DATA__" type="application/json">' + json.dumps({"props": {"pageProps": {
    "initialData": {"searchResult": {"itemStacks": [{"items": [
        {"__typename": "Product", "usItemId": "111111", "name": "Ozark Trail 24 oz Insulated Bottle", "priceInfo": {"linePrice": "$9.97"},
         "averageRating": 4.6, "numberOfReviews": 2150, "isSponsoredFlag": False},
        {"__typename": "Product", "usItemId": "222222", "name": "Hydro Flask Wide Mouth 32 oz", "priceInfo": {"linePrice": "$44.95"},
         "averageRating": 4.8, "numberOfReviews": 900, "isSponsoredFlag": True}]}]}}}}}) + "</script></body></html>")


def test_parse_bestsellers_search_product_walmart():
    from app.services import competitors as cs
    kind, cat, items = cs.parse_page(BESTSELLERS)
    assert kind == "amazon_bestsellers" and cat == "Sports Water Bottles" and len(items) == 4
    a = items[0]
    assert (a["market_id"], a["rank"], a["price"], a["rating"], a["review_count"]) == ("B0AAAAAAA1", 1, 24.95, 4.7, 52301)
    assert a["title"].startswith("HydroPeak Insulated") and items[1]["review_count"] == 1200

    kind, cat, items = cs.parse_page(SEARCH)
    assert kind == "amazon_search" and cat == "Search: insulated water bottle"
    owala, sp = items[0], items[1]
    assert owala["position"] == 1 and sp["position"] == 2 and owala["monthly_bought"] == 10000 and owala["badges"] == ["Best Seller"]
    assert owala["review_count"] == 3410 and owala["sponsored"] is False
    assert sp["sponsored"] is True and sp["title"] == "Brand X Insulated Water Bottle Leak Proof Lid"

    kind, _, items = cs.parse_page(PRODUCT_PAGE)
    p = items[0]
    assert kind == "amazon_product" and p["market_id"] == "B0AAAAAAA2" and len(p["bullets"]) == 2
    assert p["bsr_rank"] == 1234 and "Sports" in p["bsr"] and p["has_aplus"] and p["has_video"] and p["image_count"] == 3
    assert len(p["reviews"]) == 3 and p["brand"] == "Owala"

    kind, cat, items = cs.parse_page(WALMART_SEARCH)
    assert kind == "walmart_search" and [i["market_id"] for i in items] == ["111111", "222222"]
    assert items[0]["price"] == 9.97 and items[1]["sponsored"] is True and items[0]["review_count"] == 2150


def test_benchmark_numbers_and_missing_keywords():
    from app.services import competitors as cs
    comps = [
        {"title": "HydroPeak Insulated Water Bottle with Straw Lid 32 oz Stainless Steel", "price": 20.0, "rating": 4.5, "sources": ["search"]},
        {"title": "Owala Insulated Water Bottle with Straw Lid 24 oz Leak Proof", "price": 30.0, "rating": 4.7, "sources": ["search"]},
        {"title": "Takeya Kids Insulated Water Bottle Straw Lid", "price": 40.0, "rating": 4.6, "sources": ["search"], "sponsored": True},
        {"title": "Glass bottle", "price": 10.0, "included": False},
    ]
    b = cs.benchmark({"name": "Trail Bottle", "price": 25.0, "description": "Stainless steel bottle", "features": ["Leak proof lid"]}, comps)
    assert b["listings"] == 3 and b["price"]["median"] == 30.0 and b["your_price_percentile"] == 0.33
    kw = {k["term"]: k for k in b["keywords"]}
    assert kw["insulated water"]["titles"] == 3 and kw["insulated water"]["in_your_listing"] is False
    assert "straw lid" in b["missing_keywords"] and "stainless steel" not in b["missing_keywords"]
    assert b["sponsored_share"] == 0.333


def test_competitor_brand_and_product_line_names_are_never_suggested():
    from app.services import competitors as cs
    titles = ["HP Envy 6155e Wireless All-in-One Color Inkjet Printer", "HP DeskJet 2952 Wireless All-in-One Color Inkjet Printer",
              "Canon PIXMA TS3722 Wireless All-in-One Inkjet Printer", "Epson Expression Home XP-4255 Wireless Color Inkjet Printer",
              "(Open Box) HP Envy 6455e Wireless Color Inkjet Printer", "HydroPeak Insulated Water Bottle 32oz Wireless"]
    b = cs.benchmark({"name": "Printer", "brand": "Acme"}, [{"title": t} for t in titles])
    terms = {k["term"] for k in b["keywords"]}
    assert "wireless" in " ".join(terms) and "inkjet printer" in terms
    for banned in ("hp", "envy", "hp envy", "deskjet", "canon", "pixma", "epson", "hydropeak"):
        assert banned not in terms, banned
    names = cs.name_words([{"title": t} for t in titles], {})
    assert {"envy", "deskjet", "pixma", "hp", "canon", "epson"} <= names
    assert not {"insulated", "water", "bottle", "wireless", "color"} & names  # "32oz" is a size, not a model number


def test_import_merges_pages_and_skips_own_listing(client):
    pid = client.post("/api/products", json={"name": "Trail Bottle", "asin": "B08N5WRWNW", "price": 21}).json()["id"]
    r = client.post(f"/api/products/{pid}/competitors/import", json={"sources": [
        {"name": "bestsellers.html", "content": BESTSELLERS}, {"name": "search.html", "content": SEARCH},
        {"name": "owala.html", "content": PRODUCT_PAGE}, {"name": "junk.html", "content": "<html><body>hello</body></html>"}]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sources"][0]["skipped_own"] == 1 and body["sources"][0]["added"] == 3
    assert body["sources"][1]["added"] == 2 and body["sources"][1]["updated"] == 1  # Owala was already on the list
    assert body["sources"][2]["updated"] == 1 and "recognise" in body["sources"][3]["error"]
    assert body["total"] == 5
    items = client.get(f"/api/products/{pid}/competitors").json()["items"]
    owala = next(i for i in items if i["market_id"] == "B0AAAAAAA2")
    assert owala["sources"] == ["bestsellers", "product_page", "search"] and owala["rank"] == 2 and owala["position"] == 1
    assert owala["monthly_bought"] == 10000 and owala["has_details"] and owala["review_samples"] == 3
    assert [i["market_id"] for i in items][:2] == ["B0AAAAAAA1", "B0AAAAAAA2"]  # ordered by best-seller rank
    sponsored = next(i for i in items if i["market_id"] == "B0SPONSOR1")
    client.patch(f"/api/products/{pid}/competitors/{sponsored['id']}", json={"included": False})
    bench = client.get(f"/api/products/{pid}/competitors/benchmark").json()
    assert bench["listings"] == 4 and bench["with_details"] == 1 and bench["aplus_share"] == 1.0
    assert bench["bsr"][0]["bsr"].startswith("#1,234 in Sports")


def test_category_analysis_counts_competitor_complaints(client, monkeypatch):
    from app.ai import fallback_manager as fm
    seen = {}

    def fake(req, *, purpose, preferred=None, strict=False):
        p = req.prompt
        if "For EVERY review" in p:
            out = [{"n": int(n), "praise": ["keeps water cold"] if "cold" in t.lower() else [],
                    "complaints": ["lid leaks"] if "leak" in t.lower() else [], "requests": [], "use_case": ""}
                   for n, t in re.findall(r"\[(\d+)\] (.+)", p)]
            return TextResult(text=json.dumps({"reviews": out}), provider="fake", model="fake-1")
        if "Group labels" in p:
            return TextResult(text=json.dumps({"themes": []}), provider="fake", model="fake-1")
        seen["synth"] = p
        return TextResult(text=json.dumps({
            "summary": "Straw lids win; leaks are the shared weakness.", "title_formula": "Brand + Insulated Water Bottle + Straw Lid + size",
            "competitor_weaknesses": [{"weakness": "Leaky lids", "evidence": "lid leaks: 2 reviews", "opportunity": "Prove the seal"}],
            "keywords_to_add": ["straw lid", "made-up keyword"], "listing_recommendations": ["Add the size to the title"]}),
            provider="fake", model="fake-1")
    monkeypatch.setattr(fm, "generate_text", fake)
    pid = client.post("/api/products", json={"name": "Trail Bottle", "price": 21, "description": "A bottle."}).json()["id"]
    client.post(f"/api/products/{pid}/competitors/import", json={"sources": [
        {"name": "b", "content": BESTSELLERS}, {"name": "p", "content": PRODUCT_PAGE}]})
    assert client.post(f"/api/products/{pid}/competitors/analyze", json={}).status_code == 202
    assert run_pending_jobs() == ["succeeded"]
    res = client.get(f"/api/products/{pid}/competitors/analysis").json()["result"]
    leaks = res["competitor_review_themes"]["complaints"][0]
    assert (leaks["theme"], leaks["reviews"], leaks["competitors"]) == ("lid leaks", 2, 1)
    assert leaks["quotes"][0]["competitor"].startswith("Owala")
    assert res["keywords_to_add"] == ["straw lid"]  # invented keywords are dropped
    assert res["coverage"]["listings"] == 4 and res["coverage"]["reviews_analysed"] == 3
    assert "MISSING KEYWORDS" in seen["synth"] and "lid leaks: 2 of 3 competitor reviews" in seen["synth"]

    # Product research and listing copy now use the category analysis.
    from app.services import copywriting as cw
    prompts = []
    monkeypatch.setattr(cw.fm, "generate_text", lambda req, **k: prompts.append(req.prompt) or TextResult(
        text=json.dumps({"summary": "s"}), provider="fake", model="fake-1"))
    client.post(f"/api/products/{pid}/research", json={})
    assert run_pending_jobs() == ["succeeded"]
    assert "Category analysis of top-performing competitor listings" in prompts[-1] and "straw lid" in prompts[-1]
    assert client.get(f"/api/products/{pid}/research").json()[0]["result"] == {"summary": "s"}


def test_same_item_twice_on_one_page(client):
    """Real Walmart/Amazon search pages show some items twice (sponsored slot + organic slot)."""
    pid = client.post("/api/products", json={"name": "Y"}).json()["id"]
    page = SEARCH.replace("</body>", _search_item(4, "B0AAAAAAA4", "Takeya Actives Insulated Bottle 24 oz", "29.99",
                                                  sponsored=True) + "</body>")
    r = client.post(f"/api/products/{pid}/competitors/import", json={"sources": [{"name": "s", "content": page}]})
    assert r.status_code == 200, r.text
    assert r.json()["sources"][0]["added"] == 3 and r.json()["total"] == 3
    takeya = next(i for i in client.get(f"/api/products/{pid}/competitors").json()["items"] if i["market_id"] == "B0AAAAAAA4")
    assert takeya["position"] == 3 and takeya["sponsored"] is False


def test_captcha_and_empty_import(client):
    pid = client.post("/api/products", json={"name": "X"}).json()["id"]
    r = client.post(f"/api/products/{pid}/competitors/import", json={"sources": [
        {"name": "c", "content": "<html><form action='/errors/validateCaptcha'></form></html>"}]})
    assert r.status_code == 422 and "CAPTCHA" in r.json()["detail"]
    assert client.post(f"/api/products/{pid}/competitors/analyze", json={}).status_code == 422
