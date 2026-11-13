"""Persistent job queue backed by the `jobs` table.

Design
- Jobs are rows; workers claim with an atomic conditional UPDATE (status queued → running),
  so a job can never run twice concurrently even with several worker threads.
- CPU-heavy jobs (image/video) are limited by `heavy_job_slots` so the machine stays usable.
- Failures retry with exponential backoff up to `max_attempts`; every attempt is recorded.
- On startup, jobs left `running` by a crash/kill are re-queued (recovery).
- Cancellation: queued jobs cancel immediately; running jobs see `is_cancelled()` and stop
  cooperatively at their next checkpoint.
"""
from __future__ import annotations

import logging
import random
import threading
import time
import traceback
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Job, JobAttempt, Notification, utcnow
from app.db.session import session_scope

log = logging.getLogger("shelfcraft.jobs")


class JobCancelled(Exception):
    pass


class PermanentJobError(Exception):
    """Raise from a handler for errors that retrying cannot fix (bad input, missing asset)."""


class JobContext:
    """Passed to handlers: progress reporting and cancellation checks."""

    def __init__(self, job_id: str, payload: dict[str, Any]) -> None:
        self.job_id = job_id
        self.payload = payload

    def progress(self, fraction: float, message: str | None = None) -> None:
        # Kept in memory: handlers often hold a write transaction, and SQLite allows one writer,
        # so a second write connection here would block. The API merges live progress (see live()).
        LIVE_PROGRESS[self.job_id] = (max(0.0, min(1.0, fraction)), message)
        if self.is_cancelled():
            raise JobCancelled()

    def is_cancelled(self) -> bool:
        with session_scope() as db:
            status = db.scalar(select(Job.status).where(Job.id == self.job_id))
        return status == "cancelled"


LIVE_PROGRESS: dict[str, tuple[float, str | None]] = {}


def live(job_id: str) -> tuple[float, str | None] | None:
    return LIVE_PROGRESS.get(job_id)


Handler = Callable[[JobContext], dict[str, Any] | None]
_HANDLERS: dict[str, tuple[Handler, bool]] = {}


def job_handler(job_type: str, *, heavy: bool = False) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        _HANDLERS[job_type] = (fn, heavy)
        return fn

    return deco


def registered_types() -> list[str]:
    return sorted(_HANDLERS)


def enqueue(
    db: Session,
    job_type: str,
    payload: dict[str, Any],
    *,
    priority: int = 0,
    batch_id: str | None = None,
    project_id: str | None = None,
    session_id: str | None = None,
    idempotency_key: str | None = None,
    max_attempts: int | None = None,
) -> Job:
    if job_type not in _HANDLERS:
        raise ValueError(f"unknown job type: {job_type}")
    if idempotency_key:
        existing = db.scalar(select(Job).where(Job.idempotency_key == idempotency_key))
        if existing:
            return existing
    _, heavy = _HANDLERS[job_type]
    job = Job(
        type=job_type,
        payload=payload,
        heavy=heavy,
        priority=priority,
        batch_id=batch_id,
        project_id=project_id,
        session_id=session_id,
        idempotency_key=idempotency_key,
        max_attempts=max_attempts or get_settings().job_max_attempts,
    )
    db.add(job)
    db.flush()
    _WAKE.set()
    return job


def cancel(db: Session, job_id: str) -> bool:
    res = db.execute(
        update(Job)
        .where(Job.id == job_id, Job.status.in_(("queued", "running")))
        .values(status="cancelled", finished_at=utcnow(), message="Cancelled by user")
    )
    return res.rowcount > 0


def retry(db: Session, job_id: str) -> bool:
    res = db.execute(
        update(Job)
        .where(Job.id == job_id, Job.status.in_(("failed", "cancelled")))
        .values(status="queued", error=None, attempts=0, progress=0.0, run_after=None,
                message="Re-queued", finished_at=None)
    )
    _WAKE.set()
    return res.rowcount > 0


def recover_stale_jobs() -> int:
    """Re-queue jobs that were `running` when the process died."""
    with session_scope() as db:
        res = db.execute(
            update(Job)
            .where(Job.status == "running")
            .values(status="queued", message="Recovered after restart", started_at=None)
        )
        return res.rowcount


# ---------------------------------------------------------------- worker pool
_WAKE = threading.Event()
_STOP = threading.Event()
_heavy_sem: threading.Semaphore | None = None
_threads: list[threading.Thread] = []


def _get_heavy_sem() -> threading.Semaphore:
    global _heavy_sem
    if _heavy_sem is None:
        _heavy_sem = threading.Semaphore(max(1, get_settings().heavy_job_slots))
    return _heavy_sem


def _claim(heavy_allowed: bool) -> Job | None:
    now = datetime.now(timezone.utc)
    with session_scope() as db:
        q = (
            select(Job.id)
            .where(Job.status == "queued", or_(Job.run_after.is_(None), Job.run_after <= now))
            .order_by(Job.priority.desc(), Job.created_at)
            .limit(5)
        )
        if not heavy_allowed:
            q = q.where(Job.heavy.is_(False))
        for job_id in db.scalars(q).all():
            res = db.execute(
                update(Job)
                .where(and_(Job.id == job_id, Job.status == "queued"))
                .values(status="running", started_at=now, attempts=Job.attempts + 1, message="Running")
            )
            if res.rowcount == 1:
                db.flush()
                job = db.get(Job, job_id)
                assert job is not None
                db.add(JobAttempt(job_id=job.id, number=job.attempts))
                db.expunge(job)
                return job
    return None


def _finish(job: Job, *, ok: bool, result: dict[str, Any] | None = None, error: str | None = None,
            permanent: bool = False) -> None:
    LIVE_PROGRESS.pop(job.id, None)
    with session_scope() as db:
        current = db.get(Job, job.id)
        if current is None:
            return
        attempt = db.scalar(
            select(JobAttempt).where(JobAttempt.job_id == job.id).order_by(JobAttempt.number.desc()).limit(1)
        )
        if attempt:
            attempt.finished_at = utcnow()
            attempt.status = "succeeded" if ok else "failed"
            attempt.error = error
        if current.status == "cancelled":
            return
        if ok:
            current.status, current.result, current.progress = "succeeded", result or {}, 1.0
            current.finished_at, current.message, current.error = utcnow(), "Done", None
            return
        if not permanent and current.attempts < current.max_attempts:
            delay = min(300, (2 ** current.attempts) * 5) + random.uniform(0, 3)
            current.status = "queued"
            current.run_after = utcnow() + timedelta(seconds=delay)
            current.error = error
            current.message = f"Attempt {current.attempts} failed; retrying in {int(delay)}s"
            return
        current.status, current.error, current.finished_at = "failed", error, utcnow()
        current.message = "Failed"
        db.add(Notification(level="error", title=f"Job failed: {current.type}",
                            body=(error or "")[:500], link=f"/jobs?focus={current.id}"))


def _run_one(job: Job) -> None:
    handler, heavy = _HANDLERS.get(job.type, (None, False))
    if handler is None:
        _finish(job, ok=False, error=f"No handler for job type {job.type}", permanent=True)
        return
    ctx = JobContext(job.id, job.payload or {})
    try:
        if heavy:
            with _get_heavy_sem():
                result = handler(ctx)
        else:
            result = handler(ctx)
        _finish(job, ok=True, result=result)
    except JobCancelled:
        log.info("job %s cancelled", job.id)
        _finish(job, ok=False, error="cancelled", permanent=True)
    except PermanentJobError as e:
        log.warning("job %s permanent failure: %s", job.id, e)
        _finish(job, ok=False, error=str(e), permanent=True)
    except Exception as e:  # noqa: BLE001 - worker must survive any handler error
        log.error("job %s failed: %s\n%s", job.id, e, traceback.format_exc())
        _finish(job, ok=False, error=f"{type(e).__name__}: {e}")


def _worker_loop(index: int) -> None:
    log.info("worker %d started", index)
    while not _STOP.is_set():
        try:
            job = _claim(heavy_allowed=True)
        except Exception:  # noqa: BLE001 - DB hiccup; back off and retry
            log.exception("claim failed")
            job = None
        if job is None:
            _WAKE.wait(timeout=2.0)
            _WAKE.clear()
            continue
        _run_one(job)
    log.info("worker %d stopped", index)


def start_workers() -> None:
    if _threads:
        return
    s = get_settings()
    _get_heavy_sem()
    _STOP.clear()
    recovered = recover_stale_jobs()
    if recovered:
        log.warning("re-queued %d interrupted job(s)", recovered)
    for i in range(max(1, s.job_workers)):
        t = threading.Thread(target=_worker_loop, args=(i,), name=f"job-worker-{i}", daemon=True)
        t.start()
        _threads.append(t)


def stop_workers(timeout: float = 10.0) -> None:
    """Graceful shutdown: stop claiming; let running jobs finish up to `timeout`."""
    _STOP.set()
    _WAKE.set()
    deadline = time.time() + timeout
    for t in _threads:
        t.join(max(0.0, deadline - time.time()))
    _threads.clear()


def run_job_inline(job_id: str) -> None:
    """Test helper: claim and run one specific queued job synchronously."""
    with session_scope() as db:
        job = db.get(Job, job_id)
        assert job is not None
        db.execute(update(Job).where(Job.id == job_id)
                   .values(status="running", started_at=utcnow(), attempts=Job.attempts + 1))
        db.add(JobAttempt(job_id=job_id, number=(job.attempts or 0) + 1))
        db.flush()
        db.refresh(job)
        db.expunge(job)
    _run_one(job)
