"""Read a public Amazon / Walmart product page and turn it into product fields.

One plain GET per import with ordinary browser headers. If the marketplace answers with a CAPTCHA or block
page we stop and report it; there is deliberately no proxy rotation, CAPTCHA solving or retry loop. Automated
access may conflict with the marketplace's terms of use; it is enabled here at the user's request.
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/130.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
BLOCK_MARKERS = ("captcha", "robot check", "api-services-support@amazon.com", "verify your identity",
                 "press & hold", "px-captcha", "are you a human")


class ScrapeError(ValueError):
    pass


def _clean(s: str | None) -> str | None:
    if not s:
        return None
    s = re.sub(r"\s+", " ", s.replace("‎", "").replace("‏", "")).strip()
    return s or None


def _price(s: Any) -> float | None:
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    m = re.search(r"\d[\d,]*(?:\.\d+)?", str(s))
    try:
        return float(m.group(0).replace(",", "")) if m else None
    except ValueError:
        return None


_NETWORK_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RemoteProtocolError,
                   httpx.ReadError)


def _get(url: str, headers: dict[str, str], timeout: float = 20.0) -> httpx.Response:
    """GET with one fallback for network-level failures (not for blocks/CAPTCHAs).

    Marketplace CDNs resolve to IPv6 first; on PCs whose IPv6 route is flaky the connection stalls or drops
    (ConnectError) while IPv4 works. httpx has no automatic IPv6->IPv4 fallback, so on a network error we retry
    once over IPv4 only. This is a single reconnect, not a retry loop against bot checks.
    """
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as c:
            return c.get(url)
    except _NETWORK_ERRORS:
        transport = httpx.HTTPTransport(local_address="0.0.0.0")  # binds an IPv4 socket -> IPv4 addresses only
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers, transport=transport) as c:
            return c.get(url)


def fetch_page(url: str) -> str:
    try:
        r = _get(url, HEADERS)
    except httpx.HTTPError as e:
        raise ScrapeError(f"couldn't reach the page ({type(e).__name__}) — check your internet connection "
                          "and try the import again") from e
    if r.status_code == 404:
        raise ScrapeError("product not found (HTTP 404) — check the ID and marketplace country")
    if r.status_code >= 400:
        raise ScrapeError(f"the marketplace declined the request (HTTP {r.status_code})")
    html = r.text[:MAX_HTML]
    check_not_blocked(html)
    return html


MAX_HTML = 8_000_000


def check_not_blocked(html: str) -> None:
    head = html[:200_000].lower()
    if any(m in head for m in BLOCK_MARKERS) and "producttitle" not in head and "__next_data__" not in head:
        raise ScrapeError("the marketplace showed a CAPTCHA / bot check instead of the product page")


# ---------------------------------------------------------------- pages the user saved/copied from their own browser
_ASIN_IN_URL = re.compile(r"(?:/dp/|/gp/product/|/gp/aw/d/|/ASIN/)([A-Z0-9]{10})(?:[/?#\"']|$)", re.I)
_WALMART_IN_URL = re.compile(r"walmart\.[a-z.]+/ip/(?:[^/?#\"']+/)?(\d{6,14})", re.I)


def identify_page(html: str) -> tuple[str, str, str]:
    """Work out which marketplace product a saved/copied page is: ("amazon"|"walmart", id, canonical url).

    Used when the user opens the page in their own browser (as a normal visitor) and hands Shelfcraft the
    page source, e.g. after our single automated request was answered with a bot check.
    """
    if len(html.strip()) < 200:
        raise ScrapeError("that doesn't look like a web page; copy the whole page source (Ctrl+U, then Ctrl+A, Ctrl+C)")
    try:
        check_not_blocked(html)
    except ScrapeError:
        raise ScrapeError("this is the CAPTCHA / bot-check page, not the product page; complete the check in "
                          "your browser first, then save or copy the product page") from None
    soup = BeautifulSoup(html, "html.parser")
    canonical = soup.find("link", rel="canonical")
    canon = canonical.get("href", "") if canonical else ""
    og = soup.find("meta", property="og:url")
    candidates = [canon, og.get("content", "") if og else ""]
    low = html[:300_000].lower()

    asin_input = soup.select_one("input#ASIN, input[name='ASIN']")
    if asin_input and re.fullmatch(r"[A-Z0-9]{10}", (asin_input.get("value") or "").strip().upper()):
        asin = asin_input["value"].strip().upper()
        domain = re.search(r"https?://(?:www\.)?(amazon\.[a-z.]+)", canon or "")
        return "amazon", asin, f"https://www.{domain.group(1) if domain else 'amazon.com'}/dp/{asin}"
    for c in candidates:
        m = _ASIN_IN_URL.search(c or "")
        if m and "amazon." in c.lower():
            return "amazon", m.group(1).upper(), c.split("?")[0]
        m = _WALMART_IN_URL.search(c or "")
        if m:
            return "walmart", m.group(1), f"https://www.walmart.com/ip/{m.group(1)}"
    if "__next_data__" in low and "walmart" in low:
        nd = soup.find("script", id="__NEXT_DATA__")
        try:
            prod = json.loads(nd.string)["props"]["pageProps"]["initialData"]["data"]["product"]
            item = str(prod.get("usItemId") or "")
        except (AttributeError, json.JSONDecodeError, KeyError, TypeError):
            item = ""
        if re.fullmatch(r"\d{6,14}", item):
            return "walmart", item, f"https://www.walmart.com/ip/{item}"
    if soup.select_one("#productTitle"):
        m = _ASIN_IN_URL.search(html[:2_000_000])
        if m:
            return "amazon", m.group(1).upper(), f"https://www.amazon.com/dp/{m.group(1).upper()}"
    raise ScrapeError("couldn't recognise an Amazon or Walmart product page in what you pasted; make sure you "
                      "copied the product page itself (Ctrl+U shows its source)")


# ---------------------------------------------------------------- JSON-LD (works on many stores)
def _jsonld_product(soup: BeautifulSoup) -> dict[str, Any]:
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            d = stack.pop()
            if isinstance(d, dict):
                if "@graph" in d:
                    stack.extend(d["@graph"] if isinstance(d["@graph"], list) else [d["@graph"]])
                t = d.get("@type")
                if t == "Product" or (isinstance(t, list) and "Product" in t):
                    return d
            elif isinstance(d, list):
                stack.extend(d)
    return {}


def _from_jsonld(p: dict[str, Any]) -> dict[str, Any]:
    if not p:
        return {}
    offers = p.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    imgs = p.get("image") or []
    imgs = [imgs] if isinstance(imgs, str) else [i.get("url") if isinstance(i, dict) else i for i in imgs]
    brand = p.get("brand")
    return {"name": _clean(p.get("name")), "description": _clean(p.get("description")),
            "brand": _clean(brand.get("name") if isinstance(brand, dict) else brand),
            "price": _price(offers.get("price") or (offers.get("priceSpecification") or {}).get("price")),
            "currency": offers.get("priceCurrency"), "images": [i for i in imgs if i], "category": _clean(p.get("category"))}


# ---------------------------------------------------------------- Amazon
def parse_amazon(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    out = _from_jsonld(_jsonld_product(soup))
    t = soup.select_one("#productTitle")
    if t:
        out["name"] = _clean(t.get_text())
    bullets = [_clean(li.get_text()) for li in soup.select("#feature-bullets li span.a-list-item")]
    if not any(bullets):  # newer layout: "About this item" in the product-facts expander (or the quick-view copy)
        for sel in ("#productFactsDesktopExpander li span.a-list-item", "#pqv-feature-bullets li span.a-list-item"):
            bullets = [_clean(li.get_text()) for li in soup.select(sel)]
            if any(bullets):
                break
    out["features"] = [b for b in bullets if b and len(b) > 3][:10]
    d = soup.select_one("#productDescription")
    if d and _clean(d.get_text()):
        out["description"] = _clean(d.get_text())
    pr = soup.select_one("#corePrice_feature_div span.a-offscreen, #corePriceDisplay_desktop_feature_div span.a-offscreen, "
                         "span.a-price span.a-offscreen, #priceblock_ourprice, #priceblock_dealprice")
    if pr and _price(pr.get_text()):
        out["price"] = _price(pr.get_text())
    by = soup.select_one("#bylineInfo")
    if by:
        out["brand"] = _clean(re.sub(r"^(Visit the|Brand:)\s*|\s*Store$", "", by.get_text().strip()))
    crumbs = [_clean(a.get_text()) for a in soup.select("#wayfinding-breadcrumbs_feature_div a")]
    if crumbs:
        out["category"] = crumbs[-1]
    specs: dict[str, str] = {}
    for tr in soup.select("#productOverview_feature_div tr, #productDetails_techSpec_section_1 tr, "
                          "#productDetails_detailBullets_sections1 tr"):
        k, v = tr.find(["th", "td"]), tr.find_all("td")
        if k and v:
            kk, vv = _clean(k.get_text()), _clean(v[-1].get_text())
            if kk and vv and kk != vv and len(specs) < 25 and "review" not in kk.lower():
                specs[kk[:60]] = vv[:200]
    for li in soup.select("#detailBullets_feature_div li"):
        parts = [_clean(s.get_text()) for s in li.select("span.a-list-item > span")]
        if len(parts) >= 2 and parts[0] and parts[1] and len(specs) < 25:
            specs[parts[0].rstrip(" :")[:60]] = parts[1][:200]
    specs.pop("Customer Reviews", None)
    specs.pop("Best Sellers Rank", None)
    out["specifications"] = specs
    imgs = re.findall(r'"hiRes":"(https://[^"]+)"', html) or re.findall(r'"large":"(https://[^"]+)"', html)
    if not imgs:
        m = soup.select_one("#landingImage")
        if m:
            dyn = m.get("data-a-dynamic-image")
            imgs = list(json.loads(dyn).keys()) if dyn else [m.get("data-old-hires") or m.get("src")]
    out["images"] = list(dict.fromkeys(i for i in (imgs or out.get("images") or []) if i))[:8]
    rating = soup.select_one("#acrPopover")
    if rating and rating.get("title"):
        out["rating"] = _price(rating["title"])
    cnt = soup.select_one("#acrCustomerReviewText")
    if cnt:
        out["review_count"] = int(_price(cnt.get_text()) or 0) or None
    from app.services.reviews import parse_amazon_reviews

    out["reviews"] = parse_amazon_reviews(soup)[:30]
    if not out.get("name"):
        raise ScrapeError("couldn't find the product on that Amazon page (layout changed or blocked)")
    return out


APLUS_SELECTORS = "#aplus, #aplus_feature_div, #aplusBrandStory_feature_div, .aplus-v2, [class*=aplus-module]"


def detect_aplus(html: str) -> bool:
    """True when an Amazon page shows A+ / Brand Story content. Every product page carries the (empty) A+
    containers, so only containers with images or real text count."""
    soup = BeautifulSoup(html, "html.parser")
    for el in soup.select(APLUS_SELECTORS):
        if el.find("img") or len(el.get_text(" ", strip=True)) > 200:
            return True
    return False


# ---------------------------------------------------------------- Walmart
def parse_walmart(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    out = _from_jsonld(_jsonld_product(soup))
    nd = soup.find("script", id="__NEXT_DATA__")
    if nd and nd.string:
        try:
            data = json.loads(nd.string)["props"]["pageProps"]["initialData"]["data"]
        except (json.JSONDecodeError, KeyError, TypeError):
            data = {}
        prod = data.get("product") or {}
        if prod:
            out["name"] = _clean(prod.get("name")) or out.get("name")
            out["brand"] = _clean(prod.get("brand")) or out.get("brand")
            price = ((prod.get("priceInfo") or {}).get("currentPrice") or {})
            out["price"] = _price(price.get("price")) or out.get("price")
            out["currency"] = price.get("currencyUnit") or out.get("currency")
            imgs = [i.get("url") for i in (prod.get("imageInfo") or {}).get("allImages") or [] if i.get("url")]
            if imgs:
                out["images"] = imgs
            path = (prod.get("category") or {}).get("path") or []
            if path:
                out["category"] = _clean(path[-1].get("name"))
            short = prod.get("shortDescription")
            if short:
                out["description"] = _clean(BeautifulSoup(short, "html.parser").get_text(" "))
        idml = data.get("idml") or {}
        long = idml.get("longDescription")
        if long:
            ls = BeautifulSoup(long, "html.parser")
            feats = [_clean(li.get_text()) for li in ls.find_all("li")]
            out["features"] = [f for f in feats if f][:10]
            if not out.get("description"):
                out["description"] = _clean(ls.get_text(" "))
        if not out.get("features") and (prod.get("shortDescription") or ""):
            feats = [_clean(li.get_text()) for li in BeautifulSoup(prod["shortDescription"], "html.parser").find_all("li")]
            out["features"] = [f for f in feats if f][:10]
        specs = {}
        for s in idml.get("specifications") or []:
            if s.get("name") and s.get("value") and len(specs) < 25:
                specs[str(s["name"])[:60]] = str(s["value"])[:200]
        out["specifications"] = specs
        from app.services.reviews import parse_walmart_reviews

        rv = data.get("reviews") or {}
        out["rating"] = _price(rv.get("averageOverallRating") or (prod.get("averageRating")))
        out["review_count"] = rv.get("totalReviewCount") or prod.get("numberOfReviews")
        out["reviews"] = parse_walmart_reviews(soup)[:30]
    out["images"] = list(dict.fromkeys(out.get("images") or []))[:8]
    if not out.get("name"):
        raise ScrapeError("couldn't find the product on that Walmart page (layout changed or blocked)")
    return out


def reviews_text(reviews: list[dict[str, Any]]) -> str:
    """Format scraped reviews the way the research form expects pasted reviews."""
    lines = []
    for r in reviews:
        head = f"{r['rating']:g}★ " if r.get("rating") else ""
        head += f"{r['title']}: " if r.get("title") else ""
        lines.append(f"{head}{r['text']}")
    return "\n\n".join(lines)[:20000]


IMAGE_HEADERS = {**HEADERS, "Accept": "image/jpeg,image/png,image/webp;q=0.9,*/*;q=0.1"}  # no AVIF: we can't decode it


def download_image(url: str) -> bytes | None:
    try:
        r = _get(url, IMAGE_HEADERS)
    except httpx.HTTPError:
        return None
    if r.status_code != 200 or len(r.content) > 15_000_000:
        return None
    return r.content
