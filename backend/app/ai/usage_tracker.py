"""Records every provider call (success or failure) without secrets."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.db.models import GenerationRequest, UsageRecord
from app.db.session import session_scope


def record_attempt(*, kind: str, purpose: str, provider: str, model: str | None, ok: bool,
                   latency_ms: int, prompt: str, params: dict[str, Any], error: str | None = None,
                   input_tokens: int | None = None, output_tokens: int | None = None,
                   providers_tried: list[str] | None = None) -> None:
    with session_scope() as db:
        db.add(UsageRecord(provider=provider, model=model, kind=kind, success=ok, latency_ms=latency_ms,
                           input_tokens=input_tokens, output_tokens=output_tokens))
        db.add(GenerationRequest(kind=kind, purpose=purpose, provider=provider, model=model,
                                 status="succeeded" if ok else "failed", prompt=prompt[:4000],
                                 params=params, providers_tried=providers_tried or [provider],
                                 error=(error or None), latency_ms=latency_ms))


def usage_summary(db: Session, days: int = 30) -> list[dict[str, Any]]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = db.execute(
        select(UsageRecord.provider, UsageRecord.kind,
               func.count().label("calls"),
               func.sum(case((UsageRecord.success.is_(True), 1), else_=0)).label("ok"),
               func.coalesce(func.sum(UsageRecord.input_tokens), 0),
               func.coalesce(func.sum(UsageRecord.output_tokens), 0),
               func.avg(UsageRecord.latency_ms))
        .where(UsageRecord.created_at >= since)
        .group_by(UsageRecord.provider, UsageRecord.kind)
    ).all()
    today_counts = dict(db.execute(
        select(UsageRecord.provider, func.count()).where(UsageRecord.created_at >= today)
        .group_by(UsageRecord.provider)
    ).all())
    return [
        {"provider": p, "kind": k, "calls": c, "succeeded": int(ok or 0), "failed": c - int(ok or 0),
         "input_tokens": int(it), "output_tokens": int(ot), "avg_latency_ms": int(lat or 0),
         "today": today_counts.get(p, 0)}
        for p, k, c, ok, it, ot, lat in rows
    ]
