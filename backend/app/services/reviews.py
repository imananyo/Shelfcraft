"""Customer reviews: collect them from the sources a seller actually has, de-duplicate, and compute exact stats.

Sources (nothing here fetches marketplace pages; the user opens/saves them in their own browser):
- Amazon review pages (product page or /product-reviews/<ASIN>?pageNumber=N, any star filter), saved or copied
- Walmart product / review pages (__NEXT_DATA__ JSON)
- Any store page that publishes schema.org Product reviews (JSON-LD, e.g. Shopify review apps)
- CSV/TSV exports (Helium 10, Jungle Scout, Seller Central downloads, spreadsheets) with flexible column names
- Plain pasted text (one review per blank-line-separated block, optional leading star rating)

The AI analysis lives in review_analysis.py; everything in this module is deterministic.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import Counter
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ProductReview

MAX_REVIEW_CHARS = 5000


class ReviewParseError(ValueError):
    pass


def _clean(s: Any) -> str | None:
    if s is None:
        return None
    s = re.sub(r"\s+", " ", str(s).replace("‎", "").replace("‏", "")).strip()
    return s or None


def _num(s: Any) -> float | None:
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    m = re.search(r"\d+(?:[.,]\d+)?", str(s))
    return float(m.group(0).replace(",", ".")) if m else None


def _rating(s: Any) -> float | None:
    v = _num(s)
    return v if v is not None and 0 < v <= 5 else None


_DATE_FORMATS = ("%B %d, %Y", "%d %B %Y", "%b %d, %Y", "%d %b %Y", "%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d")


def parse_date(s: Any) -> str | None:
    """Best-effort: 'Reviewed in the United States on March 3, 2024' / '3/4/2024' / ISO → 'YYYY-MM-DD'."""
    t = _clean(s)
    if not t:
        return None
    m = re.search(r"\bon (.+)$", t)
    t = (m.group(1) if m else t).strip().rstrip(".")
    t = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", t)
    iso = re.match(r"(\d{4}-\d{2}-\d{2})", t)
    if iso:
        return iso.group(1)
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(t, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _review(text: Any, **kw: Any) -> dict[str, Any] | None:
    body = _clean(text)
    if not body or len(body) < 3:
        return None
    title = _clean(kw.get("title"))
    if title:  # newer Amazon layouts put "5.0 out of 5 stars" inside the title element
        title = _clean(re.sub(r"\d(?:[.,]\d)? out of 5 stars", " ", title)) or None
    helpful = kw.get("helpful_votes")
    if isinstance(helpful, str):
        helpful = 1 if re.match(r"\s*one\b", helpful, re.I) else int(_num(helpful.replace(",", "")) or 0) or None
    return {"text": body[:MAX_REVIEW_CHARS], "title": title and title[:300], "rating": _rating(kw.get("rating")),
            "author": (_clean(kw.get("author")) or None) and _clean(kw.get("author"))[:120],
            "review_date": kw.get("review_date") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(kw.get("review_date") or ""))
            else parse_date(kw.get("review_date")),
            "verified": kw.get("verified"), "variant": (_clean(kw.get("variant")) or None) and _clean(kw.get("variant"))[:200],
            "helpful_votes": helpful if isinstance(helpful, int) else None,
            "external_id": (_clean(kw.get("external_id")) or None) and _clean(kw.get("external_id"))[:80]}


# ---------------------------------------------------------------- HTML pages
def parse_amazon_reviews(soup: BeautifulSoup) -> list[dict[str, Any]]:
    out = []
    for rv in soup.select('[data-hook="review"]'):
        body = rv.select_one('[data-hook="review-body"]')
        if not body:
            continue
        for junk in body.select("script, style, .cr-translated-review-content-hidden, [data-hook='review-collapsed'] ~ a"):
            junk.decompose()
        stars = rv.select_one('[data-hook="review-star-rating"], [data-hook="cmps-review-star-rating"], i[class*="a-star-"]')
        title = rv.select_one('[data-hook="review-title"]')
        date = rv.select_one('[data-hook="review-date"]')
        author = rv.select_one(".a-profile-name")
        variant = rv.select_one('[data-hook="format-strip"], [data-hook="format-strip-linkless"]')
        helpful = rv.select_one('[data-hook="helpful-vote-statement"]')
        r = _review(body.get_text(" "), title=title.get_text(" ") if title else None,
                    rating=stars.get_text() if stars else None, author=author.get_text() if author else None,
                    review_date=date.get_text() if date else None,
                    verified=bool(rv.select_one('[data-hook="avp-badge"], [data-hook="avp-badge-linkless"]')),
                    variant=variant.get_text(" ") if variant else None,
                    helpful_votes=helpful.get_text() if helpful else None, external_id=rv.get("id"))
        if r:
            out.append(r)
    return out


def _find_key(obj: Any, key: str, depth: int = 0) -> Any:
    if depth > 12:
        return None
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            found = _find_key(v, key, depth + 1)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _find_key(v, key, depth + 1)
            if found is not None:
                return found
    return None


def parse_walmart_reviews(soup: BeautifulSoup) -> list[dict[str, Any]]:
    nd = soup.find("script", id="__NEXT_DATA__")
    if not nd or not nd.string:
        return []
    try:
        data = json.loads(nd.string)
    except json.JSONDecodeError:
        return []
    rv = _find_key(data, "customerReviews") or []
    extra = [x for x in (_find_key(data, "topPositiveReview"), _find_key(data, "topNegativeReview")) if isinstance(x, dict)]
    out = []
    for r in [x for x in rv if isinstance(x, dict)] + extra:
        badges = json.dumps(r.get("badges") or "").lower()
        item = _review(r.get("reviewText"), title=r.get("reviewTitle"), rating=r.get("rating"), author=r.get("userNickname"),
                       review_date=r.get("reviewSubmissionTime"), verified="verified" in badges or None,
                       helpful_votes=r.get("positiveFeedback") if isinstance(r.get("positiveFeedback"), int) else None,
                       external_id=r.get("reviewId"))
        if item:
            out.append(item)
    return out


def parse_jsonld_reviews(soup: BeautifulSoup) -> list[dict[str, Any]]:
    out = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            d = stack.pop()
            if isinstance(d, list):
                stack.extend(d)
                continue
            if not isinstance(d, dict):
                continue
            if "@graph" in d:
                stack.extend(d["@graph"] if isinstance(d["@graph"], list) else [d["@graph"]])
            reviews = d.get("review") or d.get("reviews")
            if reviews:
                for r in reviews if isinstance(reviews, list) else [reviews]:
                    if not isinstance(r, dict):
                        continue
                    author = r.get("author")
                    item = _review(r.get("reviewBody") or r.get("description"), title=r.get("name"),
                                   rating=(r.get("reviewRating") or {}).get("ratingValue") if isinstance(r.get("reviewRating"), dict) else None,
                                   author=author.get("name") if isinstance(author, dict) else author,
                                   review_date=r.get("datePublished"))
                    if item:
                        out.append(item)
    return out


def _page_identity(soup: BeautifulSoup, html: str) -> tuple[str, str | None]:
    low = html[:400_000].lower()
    canon = soup.find("link", rel="canonical")
    href = (canon.get("href") if canon else "") or ""
    m = re.search(r"/(?:dp|product-reviews|gp/product)/([A-Z0-9]{10})", href + " " + html[:400_000], re.I)
    if "amazon." in (href + low[:20000]) or soup.select_one('[data-hook="review"]'):
        return "amazon", m.group(1).upper() if m else None
    if "walmart" in low and soup.find("script", id="__NEXT_DATA__"):
        w = re.search(r"/(?:ip|reviews/product)/(?:[^/\"']+/)?(\d{6,14})", href + " " + html[:400_000])
        return "walmart", w.group(1) if w else None
    return "page", None


def parse_html(html: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    head = html[:200_000].lower()
    if ("validatecaptcha" in head or "enter the characters you see" in head or "px-captcha" in head) \
            and 'data-hook="review"' not in head and "customerreviews" not in head:
        raise ReviewParseError("this is a CAPTCHA / bot-check page; complete the check in your browser, then save the review page")
    if "ap_signin" in head and "sign-in" in head and 'data-hook="review"' not in head:
        raise ReviewParseError("this is the Amazon sign-in page; sign in in your browser, then save the review page")
    soup = BeautifulSoup(html, "html.parser")
    market, ident = _page_identity(soup, html)
    reviews = parse_amazon_reviews(soup) if market == "amazon" else []
    if market == "walmart":
        reviews = parse_walmart_reviews(soup)
    if not reviews:
        reviews = parse_jsonld_reviews(soup)
    return reviews, {"market": market, "id": ident}


# ---------------------------------------------------------------- CSV / TSV exports
_COLS = {
    "rating": ("rating", "stars", "star rating", "star", "score", "review rating", "overall rating", "rating (1-5)"),
    "title": ("title", "review title", "headline", "summary", "subject"),
    "text": ("text", "body", "review", "review text", "review body", "content", "comment", "comments", "review content",
             "reviewtext", "description", "message"),
    "author": ("author", "name", "reviewer", "reviewer name", "user", "username", "customer", "profile name"),
    "review_date": ("date", "review date", "created", "created at", "submitted", "posted", "time", "datetime"),
    "verified": ("verified", "verified purchase", "is verified", "verified buyer"),
    "variant": ("variant", "variation", "variation attributes", "options", "style", "size/color", "attributes"),
    "helpful_votes": ("helpful", "helpful votes", "helpful count", "votes", "found helpful", "helpful_votes"),
    "external_id": ("id", "review id", "review_id", "reviewid"),
}


def _norm_header(h: str) -> str:
    return re.sub(r"[^a-z0-9/() -]", "", h.strip().lower().replace("_", " "))


def parse_csv(content: str) -> list[dict[str, Any]]:
    content = content.lstrip("﻿")
    try:
        dialect = csv.Sniffer().sniff(content[:5000], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel_tab if content.split("\n", 1)[0].count("\t") > content.split("\n", 1)[0].count(",") else csv.excel
    rows = list(csv.reader(io.StringIO(content), dialect))
    if len(rows) < 2:
        raise ReviewParseError("the CSV has no data rows")
    header = [_norm_header(h) for h in rows[0]]
    idx: dict[str, int] = {}
    for field, names in _COLS.items():
        for i, h in enumerate(header):
            if h in names and field not in idx and i not in idx.values():
                idx[field] = i
    if "text" not in idx:  # fall back to the longest text column
        lengths = [sum(len(r[i]) for r in rows[1:50] if i < len(r)) for i in range(len(header))]
        if not lengths or max(lengths) == 0:
            raise ReviewParseError("couldn't find a review text column (name it 'review', 'text' or 'body')")
        idx["text"] = lengths.index(max(lengths))
    out = []
    for r in rows[1:]:
        get = lambda f: r[idx[f]] if f in idx and idx[f] < len(r) else None  # noqa: E731
        v = (get("verified") or "").strip().lower()
        item = _review(get("text"), title=get("title"), rating=get("rating"), author=get("author"),
                       review_date=get("review_date"), variant=get("variant"),
                       verified=True if v in ("yes", "true", "1", "y", "verified", "verified purchase") else
                       (False if v in ("no", "false", "0", "n") else None),
                       helpful_votes=int(_num(get("helpful_votes")) or 0) or None if get("helpful_votes") else None,
                       external_id=get("external_id"))
        if item:
            out.append(item)
    return out


# ---------------------------------------------------------------- pasted text
_LEAD_RATING = re.compile(r"^\s*(?:(\d(?:[.,]\d)?)\s*(?:★|stars?|/\s*5|out of 5 stars)|(★{1,5})(?:☆*))\s*[:\-–—]?\s*", re.I)


def parse_text(content: str) -> list[dict[str, Any]]:
    blocks = [b.strip() for b in re.split(r"\n\s*\n|\n-{3,}\n", content.replace("\r", "")) if b.strip()]
    out = []
    for b in blocks:
        rating = None
        m = _LEAD_RATING.match(b)
        if m:
            rating = _num(m.group(1)) if m.group(1) else float(len(m.group(2)))
            b = b[m.end():]
        lines = [line.strip() for line in b.split("\n") if line.strip()]
        title = lines[0] if len(lines) > 1 and len(lines[0]) <= 120 and not lines[0].endswith(".") else None
        text = " ".join(lines[1:] if title else lines)
        item = _review(text, title=title, rating=rating)
        if item:
            out.append(item)
    return out


def parse_source(kind: str, content: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """kind: html | csv | text | auto. Returns (reviews, info)."""
    c = content.strip()
    if kind == "auto":
        low = c[:2000].lower()
        if low.startswith("<") or "<html" in low or "<!doctype" in low:
            kind = "html"
        else:
            first = c.split("\n", 1)[0]
            kind = "csv" if (first.count(",") >= 2 or first.count("\t") >= 1 or first.count(";") >= 2) and \
                any(n in _norm_header(first) for n in ("review", "text", "body", "rating", "comment", "content")) else "text"
    if kind == "html":
        return parse_html(content)
    if kind == "csv":
        return parse_csv(content), {"market": "csv", "id": None}
    return parse_text(content), {"market": "paste", "id": None}


# ---------------------------------------------------------------- storage
def content_hash(r: dict[str, Any]) -> str:
    norm = re.sub(r"[^a-z0-9]+", " ", (r.get("text") or "").lower()).strip()[:2000]
    key = f"{norm}|{(r.get('author') or '').lower().strip()}|{r.get('review_date') or ''}"
    return hashlib.sha256(key.encode()).hexdigest()


def save_reviews(db: Session, product_id: str, reviews: list[dict[str, Any]], source: str) -> tuple[int, int]:
    """Insert new reviews; returns (added, duplicates). Duplicates are matched on text + author + date."""
    existing = set(db.scalars(select(ProductReview.content_hash).where(ProductReview.product_id == product_id)))
    added = dupes = 0
    for r in reviews:
        h = content_hash(r)
        if h in existing:
            dupes += 1
            continue
        existing.add(h)
        db.add(ProductReview(product_id=product_id, source=source[:20], content_hash=h,
                             **{k: r.get(k) for k in ("external_id", "rating", "title", "text", "author", "review_date",
                                                      "verified", "variant", "helpful_votes")}))
        added += 1
    db.flush()
    return added, dupes


def review_out(r: ProductReview) -> dict[str, Any]:
    return {k: getattr(r, k) for k in ("id", "source", "rating", "title", "text", "author", "review_date", "verified",
                                       "variant", "helpful_votes", "created_at")}


# ---------------------------------------------------------------- exact (non-AI) statistics
STOPWORDS = set("""a about above after again against all also am an and any are aren't as at be because been before being
below between both but by can can't cannot could couldn't did didn't do does doesn't doing don't down during each few for
from further get got had hadn't has hasn't have haven't having he her here hers herself him himself his how i i'd i'll i'm
i've if in into is isn't it it's its itself just let's me more most much my myself no nor not now of off on once one only
or other ought our ours ourselves out over own really same she should shouldn't so some such than that that's the their
theirs them themselves then there there's these they they'd they'll they're they've this those through to too under until
up us very was wasn't we we'd we'll we're we've were weren't what what's when where which while who whom why will with
won't would wouldn't you you'd you'll you're you've your yours yourself yourselves ve ll re im dont didnt doesnt cant wont
isnt wasnt product item thing things bought buy purchase purchased amazon walmart review star stars would've also even
still well use used using""".split())


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z][a-z']+", text.lower().replace("’", "'"))


def _phrases(text: str) -> set[str]:
    toks = _tokens(text)
    found: set[str] = set()
    for n in (2, 3):
        for i in range(len(toks) - n + 1):
            g = toks[i:i + n]
            if g[0] in STOPWORDS or g[-1] in STOPWORDS or sum(t in STOPWORDS for t in g) > 1:
                continue
            found.add(" ".join(g))
    return found


def top_phrases(reviews: list[dict[str, Any]], *, limit: int = 15) -> dict[str, list[dict[str, Any]]]:
    """Recurring 2-3 word phrases in positive (4-5★) vs negative (1-2★) reviews, counted by number of reviews.
    Only phrases that are more common in their own group than in the other are kept (distinctive phrases)."""
    pos = [r for r in reviews if (r.get("rating") or 0) >= 4]
    neg = [r for r in reviews if r.get("rating") is not None and r["rating"] <= 2]

    def df(group: list[dict[str, Any]]) -> Counter[str]:
        c: Counter[str] = Counter()
        for r in group:
            c.update(_phrases(f"{r.get('title') or ''}. {r.get('text') or ''}"))
        return c

    dp, dn = df(pos), df(neg)

    def pick(mine: Counter[str], other: Counter[str], n_mine: int, n_other: int) -> list[dict[str, Any]]:
        rows = []
        for ph, c in mine.most_common(400):
            if c < 2:
                break
            if n_other and other.get(ph, 0) / n_other >= c / max(n_mine, 1):
                continue
            if any(ph in r["phrase"] or r["phrase"] in ph for r in rows):  # drop overlapping n-grams
                continue
            rows.append({"phrase": ph, "reviews": c, "share": round(c / max(n_mine, 1), 3)})
            if len(rows) >= limit:
                break
        return rows

    return {"positive": pick(dp, dn, len(pos), len(neg)), "negative": pick(dn, dp, len(neg), len(pos))}


def review_stats(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    rated = [r["rating"] for r in reviews if r.get("rating")]
    hist = Counter(int(round(x)) for x in rated)
    by_variant: dict[str, list[float]] = {}
    by_month: dict[str, list[float]] = {}
    for r in reviews:
        if r.get("rating") and r.get("variant"):
            by_variant.setdefault(r["variant"], []).append(r["rating"])
        if r.get("rating") and r.get("review_date"):
            by_month.setdefault(r["review_date"][:7], []).append(r["rating"])
    verified = [r for r in reviews if r.get("verified") is not None]
    return {
        "count": len(reviews), "rated": len(rated),
        "average": round(sum(rated) / len(rated), 2) if rated else None,
        "histogram": {str(s): hist.get(s, 0) for s in (5, 4, 3, 2, 1)},
        "verified_share": round(sum(1 for r in verified if r["verified"]) / len(verified), 3) if verified else None,
        "sources": dict(Counter(r.get("source") or "paste" for r in reviews)),
        "with_dates": sum(1 for r in reviews if r.get("review_date")),
        "date_range": [min(d for d in (r.get("review_date") for r in reviews) if d),
                       max(d for d in (r.get("review_date") for r in reviews) if d)] if any(r.get("review_date") for r in reviews) else None,
        "by_variant": sorted(({"variant": k, "reviews": len(v), "average": round(sum(v) / len(v), 2)}
                              for k, v in by_variant.items() if len(v) >= 2), key=lambda x: -x["reviews"])[:12],
        "by_month": [{"month": k, "reviews": len(v), "average": round(sum(v) / len(v), 2)} for k, v in sorted(by_month.items())][-24:],
        "phrases": top_phrases(reviews),
    }
