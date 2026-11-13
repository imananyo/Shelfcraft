"""Best-effort extraction of public page metadata for brand/product auto-fill.

Rules: plain GET of a public URL with an honest User-Agent, no cookies, no login, no
JavaScript execution, no retry-around-blocks. If the site blocks us (403/429/captcha), we
report that and the user fills fields manually. Private/loopback addresses are refused (SSRF).
"""
from __future__ import annotations

import ipaddress
import re
import socket
from collections import Counter
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

UA = "ShelfcraftLocal/0.1 (personal product-catalog tool; respects robots and blocks)"
BLOCKED_HOST_HINTS = ("amazon.", "amzn.", "walmart.com")  # sites whose terms prohibit automated access


class ExtractError(ValueError):
    pass


def _check_url(url: str) -> str:
    url = url.strip()
    if not url:
        raise ExtractError("URL is required")
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if not host:
        raise ExtractError("invalid URL")
    if any(h in host for h in BLOCKED_HOST_HINTS):
        raise ExtractError("This marketplace does not permit automated page access. "
                           "Please paste the product details manually or import a CSV.")
    try:
        for info in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise ExtractError("URL resolves to a private address")
    except socket.gaierror as e:
        raise ExtractError(f"could not resolve host: {host}") from e
    return url


def fetch_html(url: str) -> tuple[str, str]:
    url = _check_url(url)
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True, headers={"User-Agent": UA}) as c:
            r = c.get(url)
    except httpx.HTTPError as e:
        raise ExtractError(f"could not fetch page: {type(e).__name__}") from e
    if r.status_code in (401, 403, 429, 503):
        raise ExtractError(f"the site declined automated access (HTTP {r.status_code}); please enter details manually")
    if r.status_code >= 400:
        raise ExtractError(f"page returned HTTP {r.status_code}")
    if "text/html" not in r.headers.get("content-type", ""):
        raise ExtractError("URL is not an HTML page")
    return str(r.url), r.text[:2_000_000]


def _meta(html: str, *names: str) -> str | None:
    for n in names:
        m = re.search(
            rf'<meta[^>]+(?:property|name)=["\']{re.escape(n)}["\'][^>]*content=["\']([^"\']+)["\']', html, re.I
        ) or re.search(
            rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\']{re.escape(n)}["\']', html, re.I
        )
        if m:
            return unescape(m.group(1)).strip()
    return None


def _title(html: str) -> str | None:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    return unescape(re.sub(r"\s+", " ", m.group(1))).strip() if m else None


def _colors(html: str) -> list[str]:
    hexes = [h.lower() for h in re.findall(r"#([0-9a-fA-F]{6})\b", html)]
    ignore = {"ffffff", "000000", "fefefe", "f5f5f5", "eeeeee", "333333", "222222", "111111", "cccccc"}
    common = [f"#{h}" for h, _ in Counter(h for h in hexes if h not in ignore).most_common(4)]
    theme = _meta(html, "theme-color")
    if theme and re.match(r"^#[0-9a-fA-F]{6}$", theme) and theme.lower() not in common:
        common.insert(0, theme.lower())
    return common[:4]


def _fonts(html: str) -> list[str]:
    fams = re.findall(r"fonts\.googleapis\.com/css2?\?family=([^&\"':]+)", html)
    return [unescape(f).replace("+", " ") for f in fams][:2]


def extract_brand_from_url(url: str) -> dict[str, Any]:
    try:
        final_url, html = fetch_html(url)
    except ExtractError as e:
        return {"ok": False, "error": str(e), "suggestions": {}}
    title = _meta(html, "og:site_name") or _title(html)
    desc = _meta(html, "og:description", "description")
    image = _meta(html, "og:image")
    return {
        "ok": True,
        "source": final_url,
        "suggestions": {
            "name": (title or "").split("|")[0].split(" – ")[0].strip()[:120] or None,
            "tagline": (desc or "")[:200] or None,
            "colors": _colors(html),
            "primary_font": (_fonts(html) or [None])[0],
            "website": final_url,
            "image_url": urljoin(final_url, image) if image else None,
        },
        "note": "Extracted from public page metadata. Review before saving.",
    }


def extract_product_from_url(url: str) -> dict[str, Any]:
    try:
        final_url, html = fetch_html(url)
    except ExtractError as e:
        return {"ok": False, "error": str(e), "suggestions": {}}
    name = _meta(html, "og:title", "twitter:title") or _title(html)
    desc = _meta(html, "og:description", "description")
    price = _meta(html, "product:price:amount", "og:price:amount")
    currency = _meta(html, "product:price:currency", "og:price:currency")
    image = _meta(html, "og:image")
    sugg: dict[str, Any] = {"name": (name or "")[:200] or None, "description": desc, "source_url": final_url,
                            "image_url": urljoin(final_url, image) if image else None}
    if price:
        try:
            sugg["price"] = float(re.sub(r"[^\d.]", "", price))
        except ValueError:
            pass
    if currency:
        sugg["currency"] = currency[:8]
    return {"ok": True, "source": final_url, "suggestions": sugg,
            "note": "Extracted from public page metadata. Review before saving."}
