"""Review collection (saved pages, CSV, pasted text), de-duplication, exact stats and the batched AI analysis."""
import json
import re

import pytest

from app.ai.base import TextResult
from tests.conftest import run_pending_jobs


@pytest.fixture(autouse=True)
def _empty_job_queue(client):
    """Other test modules may leave queued jobs; run them (without AI) so job assertions here only see our jobs."""
    run_pending_jobs()


def _amazon_review(rid, stars, title, body, date, *, verified=True, variant=None, helpful=None):
    return f"""<div data-hook="review" id="{rid}">
      <span class="a-profile-name">Shopper {rid}</span>
      <a data-hook="review-title"><i data-hook="review-star-rating"><span class="a-icon-alt">{stars}.0 out of 5 stars</span></i>
        <span>{stars}.0 out of 5 stars</span><span>{title}</span></a>
      <span data-hook="review-date">Reviewed in the United States on {date}</span>
      {f'<a data-hook="format-strip">{variant}</a>' if variant else ''}
      {'<span data-hook="avp-badge">Verified Purchase</span>' if verified else ''}
      <span data-hook="review-body"><span>{body}</span></span>
      {f'<span data-hook="helpful-vote-statement">{helpful}</span>' if helpful else ''}
    </div>"""


AMAZON_REVIEW_PAGE = (
    '<html><head><link rel="canonical" href="https://www.amazon.com/product-reviews/B08N5WRWNW" /></head><body>'
    + _amazon_review("R1", 5, "Great bottle", "Keeps drinks cold all day.", "March 3, 2024", variant="Color: Teal",
                     helpful="12 people found this helpful")
    + _amazon_review("R2", 1, "Leaks", "The lid leaks in my bag.", "April 1, 2024", verified=False,
                     helpful="One person found this helpful")
    + _amazon_review("R3", 4, "Good", "Solid, but I wish it came in a bigger size.", "May 9, 2024")
    + "</body></html>")


def test_parse_amazon_review_page():
    from app.services.reviews import parse_html
    reviews, info = parse_html(AMAZON_REVIEW_PAGE)
    assert info == {"market": "amazon", "id": "B08N5WRWNW"}
    assert [r["rating"] for r in reviews] == [5.0, 1.0, 4.0]
    first = reviews[0]
    assert first["title"] == "Great bottle"  # star text stripped from the title
    assert first["review_date"] == "2024-03-03" and first["verified"] is True and first["variant"] == "Color: Teal"
    assert first["helpful_votes"] == 12 and reviews[1]["helpful_votes"] == 1 and reviews[1]["verified"] is False
    assert first["author"] == "Shopper R1" and first["external_id"] == "R1"


def test_parse_walmart_jsonld_csv_and_text():
    from app.services import reviews as rv
    walmart = ('<html><body><script id="__NEXT_DATA__" type="application/json">' + json.dumps({"props": {"pageProps": {
        "initialData": {"data": {"reviews": {"customerReviews": [
            {"reviewId": "1", "rating": 2, "reviewTitle": "Meh", "reviewText": "Scratches easily.", "userNickname": "Al",
             "reviewSubmissionTime": "3/4/2024", "badges": [{"id": "VerifiedPurchaser"}], "positiveFeedback": 3}]}}}}}})
        + "</script><p>walmart</p></body></html>")
    w, info = rv.parse_html(walmart)
    assert info["market"] == "walmart" and w[0]["rating"] == 2 and w[0]["review_date"] == "2024-03-04" and w[0]["verified"]

    jsonld = ('<html><head><script type="application/ld+json">' + json.dumps({"@type": "Product", "name": "X", "review": [
        {"reviewBody": "Love the colour.", "reviewRating": {"ratingValue": "5"}, "author": {"name": "Bo"},
         "datePublished": "2024-02-01"}]}) + "</script></head><body>shop</body></html>")
    j, _ = rv.parse_html(jsonld)
    assert j[0]["text"] == "Love the colour." and j[0]["rating"] == 5 and j[0]["author"] == "Bo"

    csv_text = ("Title,Body,Rating,Date,Author,Verified,Variation,Helpful\n"
                "Nice,\"Works great, very quiet\",5,2024-01-02,Ann,Yes,Size: L,4\n"
                "Bad,Broke after a week,1,2024-01-05,Ben,No,,\n")
    c, info = rv.parse_source("auto", csv_text)
    assert info["market"] == "csv" and len(c) == 2
    assert c[0]["text"] == "Works great, very quiet" and c[0]["verified"] is True and c[0]["helpful_votes"] == 4
    assert c[1]["rating"] == 1 and c[1]["verified"] is False

    t, info = rv.parse_source("auto", "5★ Love it\nBest purchase this year.\n\n2 stars: Too small for my hands.\n\n★★★ Okay overall.")
    assert info["market"] == "paste" and [x["rating"] for x in t] == [5, 2, 3]
    assert t[0]["title"] == "Love it" and t[0]["text"] == "Best purchase this year."


def test_parse_dates():
    from app.services.reviews import parse_date
    assert parse_date("Reviewed in the United Kingdom on 3 March 2024") == "2024-03-03"
    assert parse_date("Reviewed in the United States on March 3rd, 2024") == "2024-03-03"
    assert parse_date("2024-05-06T10:00:00Z") == "2024-05-06" and parse_date("someday") is None


def test_captcha_and_signin_pages_are_explained():
    from app.services.reviews import ReviewParseError, parse_html
    with pytest.raises(ReviewParseError, match="CAPTCHA"):
        parse_html("<html><form action='/errors/validateCaptcha'></form></html>")
    with pytest.raises(ReviewParseError, match="sign-in"):
        parse_html("<html><form name='signIn' action='/ap/signin'>Sign-In</form><span>ap_signin</span></html>")


def _product(client, **kw):
    r = client.post("/api/products", json={"name": "Trail Bottle", "category": "Water Bottles", **kw})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_import_dedupe_stats_list_delete(client):
    pid = _product(client, asin="B08N5WRWNW")
    r = client.post(f"/api/products/{pid}/reviews/import", json={"sources": [
        {"name": "page1.html", "content": AMAZON_REVIEW_PAGE},
        {"name": "pasted", "content": "1★ Leaks\nThe lid leaks in my bag."},  # no author/date: a separate entry
        {"name": "captcha.html", "content": "<html><form action='/errors/validateCaptcha'></form></html>"}]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["added"] == 4 and body["total"] == 4
    assert body["sources"][0]["source"] == "amazon" and "warning" not in body["sources"][0]
    assert "CAPTCHA" in body["sources"][2]["error"]
    # Same page again (e.g. saved twice) adds nothing.
    again = client.post(f"/api/products/{pid}/reviews/import", json={"sources": [{"name": "p", "content": AMAZON_REVIEW_PAGE}]})
    assert again.json()["added"] == 0 and again.json()["duplicates"] == 3
    # A page for another ASIN is accepted with a warning (variations share reviews).
    other = client.post(f"/api/products/{pid}/reviews/import", json={"sources": [
        {"name": "o", "content": AMAZON_REVIEW_PAGE.replace("B08N5WRWNW", "B0OTHER123").replace('id="R1"', 'id="R9"')
         .replace("Keeps drinks cold all day.", "Very cold drinks.")}]})
    assert "B0OTHER123" in other.json()["sources"][0]["warning"]

    stats = client.get(f"/api/products/{pid}/reviews/stats").json()
    assert stats["count"] == 5 and stats["histogram"]["1"] == 2 and stats["histogram"]["5"] == 2
    assert stats["date_range"] == ["2024-03-03", "2024-05-09"]
    lst = client.get(f"/api/products/{pid}/reviews", params={"rating": 1}).json()
    assert lst["total"] == 2 and all(i["rating"] == 1 for i in lst["items"])
    assert client.get(f"/api/products/{pid}/reviews", params={"q": "bigger"}).json()["total"] == 1
    rid = lst["items"][0]["id"]
    assert client.delete(f"/api/products/{pid}/reviews/{rid}").status_code == 204
    assert client.delete(f"/api/products/{pid}/reviews").json()["deleted"] == 4
    assert client.post(f"/api/products/{pid}/reviews/import", json={"sources": [
        {"name": "x", "content": "<html><body>nothing here</body></html>"}]}).status_code == 422


def test_phrases_are_counted_per_review():
    from app.services.reviews import top_phrases
    revs = ([{"rating": 1, "text": "The lid leaks everywhere. Lid leaks again!"}] * 1 +
            [{"rating": 2, "text": "lid leaks after one week"}] * 2 +
            [{"rating": 5, "text": "keeps drinks cold for hours"}] * 3)
    ph = top_phrases(revs)
    neg = {p["phrase"]: p["reviews"] for p in ph["negative"]}
    pos = {p["phrase"]: p["reviews"] for p in ph["positive"]}
    assert neg["lid leaks"] == 3 and "keeps drinks" in " ".join(pos) and pos[next(iter(pos))] == 3


def _fake_llm(monkeypatch):
    """Deterministic stand-in for the model: tags reviews by keyword, groups labels, writes a summary."""
    from app.ai import fallback_manager as fm
    calls = {"tag": 0, "cluster": 0, "synth": 0}

    def fake(req, *, purpose, preferred=None, strict=False):
        p = req.prompt
        if "For EVERY review" in p:
            calls["tag"] += 1
            out = []
            for n, text in re.findall(r"\[(\d+)\] (.+)", p):
                t = text.lower()
                out.append({"n": int(n),
                            "praise": ["keeps drinks cold"] if "cold" in t else (["great colour"] if "colour" in t else []),
                            "complaints": (["lid leaks"] if "leak" in t and int(n) % 2 else ["leaky lid"]) if "leak" in t else [],
                            "requests": ["bigger size"] if "bigger" in t else [], "use_case": "hiking" if "hike" in t else ""})
            return TextResult(text=json.dumps({"reviews": out}), provider="fake", model="fake-1")
        if "Group labels" in p:
            calls["cluster"] += 1
            themes = [{"name": "Lid leaks", "labels": ["lid leaks", "leaky lid"]}] if "leak" in p else []
            return TextResult(text=json.dumps({"themes": themes}), provider="fake", model="fake-1")
        calls["synth"] += 1
        assert "Lid leaks: 20 of 60 reviews" in p.replace("lid leaks", "Lid leaks")
        return TextResult(text=json.dumps({"summary": "Cold drinks, leaky lid.", "top_pain_points": [
            {"pain": "Leaks", "theme": "lid leaks", "how_to_address": "Show the seal"}], "objections": [],
            "buyer_motivations": ["hiking"], "feature_requests": ["bigger size"], "listing_recommendations": ["x"],
            "image_recommendations": ["y"], "assumptions": []}), provider="fake", model="fake-1")

    monkeypatch.setattr(fm, "generate_text", fake)
    return calls


def test_analysis_counts_every_review(client, monkeypatch):
    calls = _fake_llm(monkeypatch)
    pid = _product(client)
    lines = []
    for i in range(60):  # 20 leak complaints (two wordings), 30 cold praises, 10 bigger-size requests
        if i < 20:
            lines.append(f"1★ Review {i}\nThe lid leaks on every hike number {i}.")
        elif i < 50:
            lines.append(f"5★ Review {i}\nKeeps my water cold all day, test {i}.")
        else:
            lines.append(f"4★ Review {i}\nFine but I want a bigger one, note {i}.")
    r = client.post(f"/api/products/{pid}/reviews/import", json={"sources": [{"name": "p", "content": "\n\n".join(lines)}]})
    assert r.json()["added"] == 60
    job = client.post(f"/api/products/{pid}/reviews/analyze", json={})
    assert job.status_code == 202
    assert run_pending_jobs() == ["succeeded"]
    assert calls["tag"] == 5  # 60 reviews in batches of 12: nothing truncated
    res = client.get(f"/api/products/{pid}/reviews/analysis").json()["result"]
    assert res["coverage"] == {"total_reviews": 60, "sampled": 60, "analysed": 60, "skipped": 0, "sample_note": None,
                               "ai_error": None}
    complaints = {t["theme"]: t for t in res["themes"]["complaints"]}
    assert complaints["lid leaks"]["reviews"] == 20 and complaints["lid leaks"]["avg_rating"] == 1.0
    assert complaints["lid leaks"]["share"] == round(20 / 60, 3)
    assert all("leak" in q["text"].lower() for q in complaints["lid leaks"]["quotes"])  # real quotes, not model text
    assert {t["theme"]: t["reviews"] for t in res["themes"]["praise"]} == {"keeps drinks cold": 30}
    assert res["themes"]["requests"][0] == {**res["themes"]["requests"][0], "theme": "bigger size", "reviews": 10}
    assert res["use_cases"] == [{"use_case": "hiking", "reviews": 20}]
    assert res["summary"] == "Cold drinks, leaky lid." and res["stats"]["histogram"]["1"] == 20

    # The full product research now uses the counted analysis instead of raw pasted text.
    from app.services import copywriting as cw
    seen = {}

    def research_llm(req, *, purpose, preferred=None, strict=False):
        seen["prompt"] = req.prompt
        return TextResult(text=json.dumps({"summary": "s"}), provider="fake", model="fake-1")
    monkeypatch.setattr(cw.fm, "generate_text", research_llm)
    client.post(f"/api/products/{pid}/research", json={})
    assert run_pending_jobs() == ["succeeded"]
    assert "lid leaks (20/60)" in seen["prompt"]
    # ...and the Intelligence tab still shows the full research, not the review analysis.
    assert client.get(f"/api/products/{pid}/research").json()[0]["result"] == {"summary": "s"}


def test_analysis_without_ai_keeps_exact_stats(client):
    pid = _product(client)
    client.post(f"/api/products/{pid}/reviews/import", json={"sources": [{"name": "p", "content": "5★ Great\nLove it."}]})
    client.post(f"/api/products/{pid}/reviews/analyze", json={})
    assert run_pending_jobs() == ["succeeded"]  # tests have no AI provider reachable
    res = client.get(f"/api/products/{pid}/reviews/analysis").json()["result"]
    assert res["stats"]["count"] == 1 and res["coverage"]["analysed"] == 0 and res["coverage"]["ai_error"]


def test_stratified_sample_keeps_rating_mix():
    from app.services.review_analysis import stratified_sample
    revs = [{"rating": 5}] * 800 + [{"rating": 1}] * 200
    s = stratified_sample(revs, 100)
    assert len(s) == 100 and sum(1 for r in s if r["rating"] == 1) == 20
