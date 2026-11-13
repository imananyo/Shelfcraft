"""Background job monitoring and control."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Job
from app.db.session import get_db
from app.jobs import queue
from app.routers.common import get_or_404

router = APIRouter(prefix="/jobs", tags=["jobs"])

JOB_LABELS = {
    "listing_copy": "Listing copy", "product_research": "Product research", "image_generate": "Image generation",
    "image_edit": "Image edit", "factory_item": "Factory item", "video_render": "Video render",
    "inspire_analyze": "Reference analysis", "inspire_generate": "Reference-guided creative",
    "listing_images": "Listing image set", "aplus_generate": "A+ content",
}


def job_out(j: Job) -> dict[str, Any]:
    progress, message = j.progress, j.message
    if j.status == "running" and (lv := queue.live(j.id)):
        progress, message = lv[0], lv[1] or message
    return {
        "id": j.id, "type": j.type, "label": JOB_LABELS.get(j.type, j.type), "status": j.status,
        "progress": progress, "message": message, "error": j.error, "result": j.result,
        "attempts": j.attempts, "max_attempts": j.max_attempts, "batch_id": j.batch_id,
        "project_id": j.project_id, "created_at": j.created_at, "started_at": j.started_at,
        "finished_at": j.finished_at, "payload_summary": {k: v for k, v in (j.payload or {}).items()
                                                          if k in ("product_id", "creative_type", "title", "kind")},
    }


@router.get("")
def list_jobs(status: str | None = None, batch_id: str | None = None, type: str | None = None,
              limit: int = Query(50, le=500), db: Session = Depends(get_db)) -> dict[str, Any]:
    stmt = select(Job)
    if status:
        stmt = stmt.where(Job.status.in_(status.split(",")))
    if batch_id:
        stmt = stmt.where(Job.batch_id == batch_id)
    if type:
        stmt = stmt.where(Job.type == type)
    rows = db.scalars(stmt.order_by(Job.created_at.desc()).limit(limit)).all()
    counts = dict(db.execute(select(Job.status, func.count()).group_by(Job.status)).all())
    return {"items": [job_out(j) for j in rows], "counts": counts}


@router.get("/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    j = get_or_404(db, Job, job_id)
    out = job_out(j)
    out["attempt_log"] = [{"number": a.number, "status": a.status, "error": a.error,
                           "started_at": a.started_at, "finished_at": a.finished_at} for a in j.job_attempts]
    return out


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    get_or_404(db, Job, job_id)
    if not queue.cancel(db, job_id):
        raise HTTPException(409, "job is not queued or running")
    return {"ok": True}


@router.post("/{job_id}/retry")
def retry_job(job_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    get_or_404(db, Job, job_id)
    if not queue.retry(db, job_id):
        raise HTTPException(409, "only failed or cancelled jobs can be retried")
    return {"ok": True}
