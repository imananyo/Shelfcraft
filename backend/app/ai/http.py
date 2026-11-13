"""Shared HTTP plumbing for hosted adapters: timeouts and status → typed error mapping."""
from __future__ import annotations

from typing import Any

import httpx

from app.ai.base import (
    ProviderAuthError,
    ProviderBadResponse,
    ProviderRateLimited,
    ProviderRefused,
    ProviderUnavailable,
    redact,
)

DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)


def request_json(
    provider: str,
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: Any = None,
    secrets: list[str | None] | None = None,
    timeout: httpx.Timeout | float = DEFAULT_TIMEOUT,
    expect_binary: bool = False,
) -> Any:
    secrets = secrets or []
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.request(method, url, headers=headers, json=json_body)
    except httpx.TimeoutException as e:
        raise ProviderUnavailable(provider, f"timeout: {type(e).__name__}") from None
    except httpx.HTTPError as e:
        raise ProviderUnavailable(provider, redact(f"network error: {e}", secrets)) from None

    if resp.status_code == 429:
        ra = resp.headers.get("retry-after")
        try:
            retry_after = float(ra) if ra else None
        except ValueError:
            retry_after = None
        raise ProviderRateLimited(provider, "rate limited (HTTP 429)", retry_after)
    if resp.status_code in (401,):
        raise ProviderAuthError(provider, "authentication failed — check the API key")
    if resp.status_code in (402, 403):
        body = redact(resp.text[:300], secrets)
        raise ProviderRefused(provider, f"HTTP {resp.status_code}: {body}")
    if resp.status_code >= 500:
        raise ProviderUnavailable(provider, f"HTTP {resp.status_code}")
    if resp.status_code >= 400:
        raise ProviderBadResponse(provider, redact(f"HTTP {resp.status_code}: {resp.text[:400]}", secrets))
    if expect_binary:
        return resp.content
    try:
        return resp.json()
    except ValueError:
        raise ProviderBadResponse(provider, "response was not JSON") from None
