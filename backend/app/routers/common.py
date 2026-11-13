"""Shared router helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypeVar

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import AuditEvent, Base

M = TypeVar("M", bound=Base)


def get_or_404(db: Session, model: type[M], obj_id: str, *, include_deleted: bool = False) -> M:
    obj = db.get(model, obj_id)
    if obj is None or (not include_deleted and getattr(obj, "deleted_at", None) is not None):
        raise HTTPException(status_code=404, detail=f"{model.__name__} not found")
    return obj


def soft_delete(db: Session, obj: Any) -> None:
    obj.deleted_at = datetime.now(timezone.utc)
    audit(db, "delete", type(obj).__name__, obj.id)


def audit(db: Session, action: str, entity_type: str | None = None, entity_id: str | None = None,
          **detail: Any) -> None:
    db.add(AuditEvent(action=action, entity_type=entity_type, entity_id=entity_id, detail=detail))


def apply_updates(obj: Any, data: dict[str, Any]) -> None:
    for k, v in data.items():
        setattr(obj, k, v)
