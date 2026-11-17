"""Top-performing listings in a category, from pages the user saved in their own browser.

Supported pages (Shelfcraft never requests them itself):
- Amazon Best Sellers list (/zgbs/..., /gp/bestsellers/...): rank, ASIN, title, price, rating, review count
- Amazon search results (/s?k=...): position, sponsored flag, badges, "N bought in past month", price, rating, reviews
- Amazon / Walmart product pages: bullets, description, specs, image count, video, A+ content, Best Sellers Rank, reviews
- Walmart search / browse results (__NEXT_DATA__ itemStacks)

`benchmark()` turns the collected listings into exact numbers (no AI): price/rating/review distributions, title
length, the title keywords top listings share (and whether your product uses them), bullets, images, video, A+.
"""
from __future__ import annotations

import hashlib
import json
import re
import statistics
from collections import Counter
from typing import Any

from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CompetitorListing
from app.services.reviews import STOPWORDS, content_hash, parse_amazon_reviews, parse_walmart_reviews


class CompetitorParseError(ValueError):
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
    m = re.search(r"\d[\d,]*(?:\.\d+)?", str(s))
    try:
        return float(m.group(0).replace(",", "")) if m else None
    except ValueError:
        return None


def _count(s: Any) -> int | None:
    """'(12,345)' → 12345, '1.2K' → 1200, '3K+' → 3000."""
    t = _clean(s)
    if not t:
        return None
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*([KkMm])?", t)
    if not m:
        return None
    v = float(m.group(1).replace(",", ""))
    mult = {"k": 1_000, "m": 1_000_000}.get((m.group(2) or "").lower(), 1)
    return int(v * mult)


def _rating(s: Any) -> float | None:
    m = re.search(r"(\d(?:[.,]\d)?) out of 5", str(s or ""))
    v = float(m.group(1).replace(",", ".")) if m else _num(s)
    return v if v is not None and 0 < v <= 5 else None


_PRICE = re.compile(r"([$£€₹¥]|USD|EUR|GBP|INR|CAD|AUD)\s?(\d[\d,]*(?:\.\d{1,2})?)")
_CURRENCY = {"$": "USD", "£": "GBP", "€": "EUR", "₹": "INR", "¥": "JPY"}


def _price(s: Any) -> tuple[float | None, str | None]:
    m = _PRICE.search(str(s or ""))
    if not m:
        return None, None
    return float(m.group(2).replace(",", "")), _CURRENCY.get(m.group(1), m.group(1))


def _asin_from(el: Any) -> str | None:
    for node in [el, *el.select("[data-asin]")]:
        a = (node.get("data-asin") or "").strip().upper() if hasattr(node, "get") else ""
        if re.fullmatch(r"[A-Z0-9]{10}", a):
            return a
    for a in el.select("a[href]"):
        m = re.search(r"/dp/([A-Z0-9]{10})", a["href"], re.I)
        if m:
            return m.group(1).upper()
    return None


def _domain(soup: BeautifulSoup, html: str) -> str:
    canon = soup.find("link", rel="canonical")
    m = re.search(r"(amazon\.[a-z.]+)", (canon.get("href") if canon else "") or html[:50_000])
    return m.group(1) if m else "amazon.com"


# ---------------------------------------------------------------- Amazon list pages
def parse_amazon_bestsellers(soup: BeautifulSoup, html: str) -> tuple[str | None, list[dict[str, Any]]]:
    h1 = soup.select_one("h1, #zg_banner_text")
    category = _clean(re.sub(r"^\s*(Amazon )?Best ?Sellers in\s*:?\s*", "", h1.get_text(" "), flags=re.I)) if h1 else None
    dom = _domain(soup, html)
    items = soup.select("#gridItemRoot") or soup.select(".zg-grid-general-faceout") or soup.select("li.zg-item-immersion")
    out = []
    for i, it in enumerate(items, 1):
        asin = _asin_from(it)
        if not asin:
            continue
        badge = it.select_one(".zg-bdg-text, .zg-badge-text")
        texts = [_clean(a.get_text(" ")) for a in it.select("a[href*='/dp/']")]
        texts = [t for t in texts if t and "out of 5 stars" not in t and not _PRICE.fullmatch(t) and len(t) > 12]
        img = it.select_one("img")
        title = max(texts, key=len) if texts else (_clean(img.get("alt")) if img else None)
        stars = it.select_one(".a-icon-alt, i[class*='a-star'] span")
        rev = next((s for s in it.select("a[href*='product-reviews'] span, span.a-size-small")
                    if re.fullmatch(r"\(?[\d,.]+[KkMm]?\+?\)?", (s.get_text() or "").strip())), None)
        price, cur = _price(" ".join(s.get_text(" ") for s in it.select("span[class*='price'], .p13n-sc-price, span.a-color-price")) or it.get_text(" "))
        out.append({"market": "amazon", "market_id": asin, "url": f"https://www.{dom}/dp/{asin}", "title": title,
                    "rank": int(_num(badge.get_text()) or i) if badge else i, "rating": _rating(stars.get_text() if stars else None),
                    "review_count": _count(rev.get_text()) if rev and "out of" not in rev.get_text() else None,
                    "price": price, "currency": cur, "image_url": img.get("src") if img else None,
                    "category": category, "sources": ["bestsellers"]})
    return category, out


def parse_amazon_search(soup: BeautifulSoup, html: str) -> tuple[str | None, list[dict[str, Any]]]:
    box = soup.select_one("#twotabsearchtextbox")
    query = _clean(box.get("value")) if box else None
    dom = _domain(soup, html)
    out = []
    n = 0
    for it in soup.select('div[data-component-type="s-search-result"][data-asin]'):
        asin = (it.get("data-asin") or "").upper()
        if not re.fullmatch(r"[A-Z0-9]{10}", asin):
            continue
        n += 1
        h2 = it.select_one("h2")
        title = _clean(h2.get("aria-label") or h2.get_text(" ")) if h2 else None
        if title:
            title = re.sub(r"^Sponsored Ad\s*[-–]\s*", "", title)
        pr = it.select_one("span.a-price:not(.a-text-price) span.a-offscreen") or it.select_one("span.a-price span.a-offscreen")
        price, cur = _price(pr.get_text() if pr else None)
        stars = it.select_one("span.a-icon-alt")
        rev = (it.select_one("a[href*='customerReviews'] span.a-size-base, span.a-size-base.s-underline-text")
               or it.select_one("a[aria-label*='ratings'], span[aria-label*='ratings']"))
        rev_txt = (rev.get("aria-label") or rev.get_text()) if rev else None
        text = it.get_text(" ")
        bought = re.search(r"([\d.,]+[KkMm]?)\+?\s+bought in past month", text)
        sponsored = bool(it.select_one(".puis-sponsored-label-text, .s-sponsored-label-text, [data-component-type='sp-sponsored-result']")) \
            or bool(re.search(r"\bSponsored\b", " ".join(s.get_text(" ") for s in it.select("span.a-color-secondary, .puis-label-popover-default, a.puis-label-popover"))))
        badges = sorted({b for b in (_clean(x.get_text(" ")) for x in it.select("span.a-badge-text, span.a-badge-label-inner")) if b})
        if "Amazon's Choice" in text and "Amazon's Choice" not in badges:
            badges.append("Amazon's Choice")
        img = it.select_one("img.s-image")
        out.append({"market": "amazon", "market_id": asin, "url": f"https://www.{dom}/dp/{asin}", "title": title,
                    "position": n, "price": price, "currency": cur,
                    "rating": _rating(stars.get_text() if stars else None), "review_count": _count(rev_txt),
                    "monthly_bought": _count(bought.group(1)) if bought else None, "sponsored": sponsored,
                    "badges": badges, "image_url": img.get("src") if img else None,
                    "category": f"Search: {query}" if query else None, "sources": ["search"]})
    return (f"Search: {query}" if query else None), out


# ---------------------------------------------------------------- product pages
def parse_product_page(html: str) -> dict[str, Any]:
    from app.services import marketplace_scrape as ms

    market, ident, url = ms.identify_page(html)
    data = (ms.parse_amazon if market == "amazon" else ms.parse_walmart)(html)
    soup = BeautifulSoup(html, "html.parser")
    item: dict[str, Any] = {
        "market": market, "market_id": ident, "url": url, "title": data.get("name"), "brand": data.get("brand"),
        "price": data.get("price"), "currency": data.get("currency"), "rating": data.get("rating"),
        "review_count": data.get("review_count"), "bullets": data.get("features") or [],
        "description": (data.get("description") or "")[:4000] or None, "specifications": data.get("specifications") or {},
        "category": data.get("category"), "reviews": data.get("reviews") or [], "sources": ["product_page"],
        "image_url": (data.get("images") or [None])[0],
    }
    if market == "amazon":
        item["image_count"] = len(set(re.findall(r'"hiRes":"(https://[^"]+)"', html))) or len(data.get("images") or []) or None
        item["has_video"] = bool(re.search(r'"videos"\s*:\s*\[\s*\{', html) or soup.select_one("#videoBlock_feature_div video, #vse-related-videos"))
        item["has_aplus"] = bool(soup.select_one("#aplus .aplus-module, #aplus_feature_div .aplus-v2, .aplus-module"))
        details = " ".join(n.get_text(" ") for n in soup.select("#detailBulletsWrapper_feature_div, #productDetails_detailBullets_sections1, #prodDetails, #detailBullets_feature_div"))
        m = re.search(r"Best Sellers Rank:?\s*#\s?([\d,]+)\s+in\s+([^(#]+)", _clean(details) or "")
        if m:
            item["bsr_rank"] = int(m.group(1).replace(",", ""))
            item["bsr"] = _clean(f"#{m.group(1)} in {m.group(2)}")[:300]
    else:
        imgs = re.findall(r'"allImages"\s*:\s*\[(.*?)\]', html)
        item["image_count"] = len(re.findall(r'"url"\s*:', imgs[0])) if imgs else len(data.get("images") or []) or None
        item["has_video"] = '"videos":[{' in html.replace(" ", "")
    return item


def parse_walmart_search(soup: BeautifulSoup) -> tuple[str | None, list[dict[str, Any]]]:
    nd = soup.find("script", id="__NEXT_DATA__")
    try:
        data = json.loads(nd.string) if nd and nd.string else {}
    except json.JSONDecodeError:
        data = {}
    from app.services.reviews import _find_key

    stacks = _find_key(data, "itemStacks") or []
    query = _find_key(data, "query") if isinstance(_find_key(data, "query"), str) else None
    if not query and soup.title:  # "wireless all in one printer - Walmart.com"
        query = _clean(re.sub(r"\s*-\s*Walmart\.com\s*$", "", soup.title.get_text(), flags=re.I))
    out = []
    n = 0
    for st in stacks if isinstance(stacks, list) else []:
        for it in (st.get("items") or []) if isinstance(st, dict) else []:
            if not isinstance(it, dict) or not it.get("usItemId") or it.get("__typename") not in (None, "Product"):
                continue
            n += 1
            pi = it.get("priceInfo") or {}
            price, cur = _price(pi.get("linePrice") or pi.get("itemPrice") or "") if isinstance(pi, dict) else (None, None)
            if price is None and isinstance(it.get("price"), (int, float)):
                price, cur = float(it["price"]), "USD"
            badges = [_clean(b.get("text") or b.get("name")) for b in ((it.get("badges") or {}).get("flags") or [])
                      if isinstance(b, dict)] if isinstance(it.get("badges"), dict) else []
            out.append({"market": "walmart", "market_id": str(it["usItemId"]), "title": _clean(it.get("name")),
                        "url": f"https://www.walmart.com/ip/{it['usItemId']}", "position": n, "price": price, "currency": cur,
                        "rating": _num(it.get("averageRating")), "review_count": int(_num(it.get("numberOfReviews")) or 0) or None,
                        "sponsored": bool(it.get("isSponsoredFlag")), "badges": [b for b in badges if b],
                        "image_url": (it.get("imageInfo") or {}).get("thumbnailUrl") or it.get("image"),
                        "category": f"Search: {query}" if query else None, "sources": ["search"]})
    return (f"Search: {query}" if query else None), out


def parse_page(html: str) -> tuple[str, str | None, list[dict[str, Any]]]:
    """Return (page_type, category label, items)."""
    head = html[:200_000].lower()
    low = html.lower()  # Walmart's __NEXT_DATA__ sits at the end of large pages
    if ("validatecaptcha" in head or "enter the characters you see" in head or "px-captcha" in head) \
            and "producttitle" not in head and "s-search-result" not in head and "gridItemRoot".lower() not in head:
        raise CompetitorParseError("this is a CAPTCHA / bot-check page; complete the check in your browser, then save the page")
    soup = BeautifulSoup(html, "html.parser")
    if soup.select_one("#gridItemRoot, .zg-grid-general-faceout, li.zg-item-immersion"):
        cat, items = parse_amazon_bestsellers(soup, html)
        return "amazon_bestsellers", cat, items
    if soup.select_one('div[data-component-type="s-search-result"]'):
        cat, items = parse_amazon_search(soup, html)
        return "amazon_search", cat, items
    if soup.select_one("#productTitle") or ('__next_data__' in low and '"usitemid"' in low and '"itemstacks"' not in low):
        try:
            item = parse_product_page(html)
        except ValueError as e:
            raise CompetitorParseError(str(e)) from e
        return f"{item['market']}_product", item.get("category"), [item]
    if '"itemstacks"' in low:
        cat, items = parse_walmart_search(soup)
        return "walmart_search", cat, items
    raise CompetitorParseError("couldn't recognise this page. Save an Amazon Best Sellers page, an Amazon or Walmart "
                               "search results page, or a competitor's product page")


# ---------------------------------------------------------------- storage (merge by marketplace id)
SCALARS = ("url", "title", "brand", "price", "currency", "rating", "review_count", "rank", "position", "bsr_rank", "bsr",
           "category", "monthly_bought", "sponsored", "description", "image_count", "has_video", "has_aplus", "image_url")


def upsert(db: Session, product_id: str, items: list[dict[str, Any]]) -> tuple[int, int]:
    """Insert or enrich competitor rows; returns (added, updated)."""
    added = updated = 0
    seen: dict[tuple[str, str], CompetitorListing] = {}  # the same item can appear twice on one page (ad + organic)
    for it in items:
        mid = str(it.get("market_id") or "")
        if not mid:
            if not it.get("url"):
                continue
            mid = hashlib.sha1(it["url"].encode()).hexdigest()[:20]
        key = (it["market"], mid)
        row = seen.get(key) or db.scalar(select(CompetitorListing).where(
            CompetitorListing.product_id == product_id, CompetitorListing.market == it["market"],
            CompetitorListing.market_id == mid))
        if row is None:
            row = CompetitorListing(product_id=product_id, market=it["market"], market_id=mid, badges=[], bullets=[],
                                    specifications={}, reviews=[], sources=[], included=True)
            db.add(row)
            added += 1
        elif key not in seen:
            updated += 1
        first_time_here = key not in seen
        seen[key] = row
        for k in SCALARS:
            v = it.get(k)
            if v is None or v == "":
                continue
            if not first_time_here and k in ("rank", "position") and getattr(row, k) is not None:
                v = min(v, getattr(row, k))  # repeated on the same page: keep the best placement
            if not first_time_here and k == "sponsored":
                v = bool(row.sponsored) and bool(v)  # sponsored only if every appearance is an ad
            setattr(row, k, v[:1000] if isinstance(v, str) and k in ("url", "image_url") else v)
        if it.get("bullets"):
            row.bullets = it["bullets"][:10]
        if it.get("specifications"):
            row.specifications = {**(row.specifications or {}), **it["specifications"]}
        if it.get("badges"):
            row.badges = sorted(set(row.badges or []) | set(it["badges"]))
        if it.get("reviews"):
            have = {content_hash(r) for r in row.reviews or []}
            row.reviews = (row.reviews or []) + [r for r in it["reviews"] if content_hash(r) not in have][:60]
        row.sources = sorted(set(row.sources or []) | set(it.get("sources") or []))
    db.flush()
    return added, updated


def competitor_out(c: CompetitorListing) -> dict[str, Any]:
    return {**{k: getattr(c, k) for k in ("id", "market", "market_id", "included", "badges", "sources", *SCALARS)},
            "bullets": c.bullets or [], "review_samples": len(c.reviews or []),
            "has_details": "product_page" in (c.sources or [])}


# ---------------------------------------------------------------- exact benchmark
def _q(values: list[float]) -> dict[str, float] | None:
    v = sorted(x for x in values if x is not None)
    if not v:
        return None
    if len(v) == 1:
        return {"min": v[0], "p25": v[0], "median": v[0], "p75": v[0], "max": v[0], "n": 1}
    qs = statistics.quantiles(v, n=4, method="inclusive")
    return {"min": v[0], "p25": round(qs[0], 2), "median": round(statistics.median(v), 2), "p75": round(qs[2], 2),
            "max": v[-1], "n": len(v)}


def _terms(text: str) -> set[str]:
    toks = [t for t in re.findall(r"[a-z0-9][a-z0-9'+-]*", (text or "").lower()) if len(t) > 1]
    uni = {t for t in toks if t not in STOPWORDS and not t.isdigit()}
    bi = {f"{a} {b}" for a, b in zip(toks, toks[1:], strict=False) if a not in STOPWORDS and b not in STOPWORDS
          and not a.isdigit()}
    return uni | bi


_MODEL = re.compile(r"^(?=.*\d)[a-z0-9-]{2,}$")  # TS3722, 6155e, xp-4255, mfc-j1260w


def name_words(comps: list[dict[str, Any]], product: dict[str, Any]) -> set[str]:
    """Brand and product-line words that must never be suggested as keywords (using another brand's or product's
    name in a listing breaks marketplace rules). Brand = first word of a title / the brand field; product line =
    words right before a model number near the start ("HP *Envy* 6155e", "Canon *PIXMA* TS3722")."""
    out: set[str] = set()
    first: Counter[str] = Counter()
    line_slot: Counter[str] = Counter()
    anywhere: Counter[str] = Counter()
    for c in comps:
        out |= set(re.findall(r"[a-z0-9]+", (c.get("brand") or "").lower()))
        words = re.sub(r"^\(.*?\)\s*", "", c.get("title") or "").lower().replace(",", " ").split()
        if not words:
            continue
        first[words[0]] += 1
        anywhere.update(set(words))
        for i, w in enumerate(words[:4]):
            if i and _MODEL.match(w) and not _SIZE.search(w):
                line_slot.update({x for x in words[1:i] if not _MODEL.match(x)})
                break
    # A brand leads its titles and a product line sits before the model number; a generic word ("insulated",
    # "wireless") mostly appears elsewhere in titles, so it is only excluded when it USUALLY holds that slot.
    out |= {w for w, n in first.items() if n / anywhere[w] >= 0.6}
    out |= {w for w, n in line_slot.items() if n / anywhere[w] >= 0.5}
    out |= set(re.findall(r"[a-z0-9]+", (product.get("brand") or "").lower()))
    return {w for w in out if len(w) > 1}


_SIZE = re.compile(r"^\d+(\.\d+)?(oz|ml|l|ltr|liter|litre|g|kg|lb|lbs|in|inch|ft|cm|mm|qt|gal|pack|pk|pcs|ct|w|v|mah|gb|tb)$")


def _order(c: dict[str, Any]) -> tuple[int, int]:
    return (c.get("rank") or 10_000, c.get("position") or 10_000)


def benchmark(product: dict[str, Any], comps: list[dict[str, Any]]) -> dict[str, Any]:
    """Exact numbers about the collected listings, compared with the user's product. `product` needs name, price,
    description, features (list), bullets (optional list), brand (optional)."""
    comps = sorted([c for c in comps if c.get("included", True)], key=_order)
    organic = [c for c in comps if not c.get("sponsored")]
    titles = [c["title"] for c in comps if c.get("title")]
    detailed = [c for c in comps if "product_page" in (c.get("sources") or [])]
    mine_text = " ".join([product.get("name") or "", product.get("description") or "",
                          *(product.get("features") or []), *(product.get("bullets") or [])])
    mine = _terms(mine_text)
    names = name_words(comps, product)
    df: Counter[str] = Counter()
    for t in titles:
        df.update({term for term in _terms(t) if not set(term.split()) & names})
    keywords = []
    for term, n in df.most_common(200):
        share = n / len(titles)
        if share < 0.15 or n < 2:
            break
        if " " not in term and any(term in k["term"].split() and k["titles"] >= n * 0.8 for k in keywords):
            continue  # a bigram already covers this word
        keywords.append({"term": term, "titles": n, "share": round(share, 3), "in_your_listing": term in mine})
        if len(keywords) >= 30:
            break
    prices = [c["price"] for c in comps if c.get("price")]
    my_price = product.get("price")
    title_chars = [len(t) for t in titles]
    bullet_counts = [len(c.get("bullets") or []) for c in detailed if c.get("bullets")]
    bullet_chars = [statistics.mean(len(b) for b in c["bullets"]) for c in detailed if c.get("bullets")]

    def share(rows: list[dict[str, Any]], key: str) -> float | None:
        vals = [r.get(key) for r in rows if r.get(key) is not None]
        return round(sum(1 for v in vals if v) / len(vals), 3) if vals else None

    return {
        "listings": len(comps), "organic": len(organic), "with_details": len(detailed),
        "categories": [k for k, _ in Counter(c.get("category") for c in comps if c.get("category")).most_common(5)],
        "price": _q(prices), "your_price": my_price,
        "your_price_percentile": round(sum(1 for p in prices if p < my_price) / len(prices), 2) if my_price and prices else None,
        "rating": _q([c["rating"] for c in comps if c.get("rating")]),
        "review_count": _q([c["review_count"] for c in comps if c.get("review_count")]),
        "monthly_bought": _q([c["monthly_bought"] for c in comps if c.get("monthly_bought")]),
        "title_chars": _q(title_chars), "title_words": _q([len(t.split()) for t in titles]),
        "your_title_chars": len(product.get("title") or product.get("name") or "") or None,
        "keywords": keywords,
        "missing_keywords": [k["term"] for k in keywords if not k["in_your_listing"]],
        "bullets": {"count": _q(bullet_counts), "avg_chars": _q(bullet_chars)},
        "images": _q([c["image_count"] for c in detailed if c.get("image_count")]),
        "video_share": share(detailed, "has_video"), "aplus_share": share(detailed, "has_aplus"),
        "sponsored_share": (lambda s: round(sum(1 for c in s if c.get("sponsored")) / len(s), 3) if s else None)(
            [c for c in comps if "search" in (c.get("sources") or [])]),
        "badges": dict(Counter(b for c in comps for b in c.get("badges") or [])),
        "bsr": [{"title": (c.get("title") or "")[:80], "bsr": c.get("bsr")} for c in comps if c.get("bsr")][:20],
        "top": [{"title": (c.get("title") or "")[:140], "rank": c.get("rank"), "position": c.get("position"),
                 "price": c.get("price"), "rating": c.get("rating"), "reviews": c.get("review_count"),
                 "bought": c.get("monthly_bought")} for c in comps[:10]],
    }
