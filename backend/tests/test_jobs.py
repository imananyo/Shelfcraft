"""Persistent job queue: retries, permanent failure, cancel, recovery, idempotency."""
from __future__ import annotations

from typing import Any

from app.db.models import Job
from app.db.session import session_scope
from app.jobs import queue
from app.jobs.queue import JobContext, PermanentJobError, job_handler

CALLS: dict[str, int] = {}


@job_handler("test_flaky")
def _flaky(ctx: JobContext) -> dict[str, Any]:
    CALLS["flaky"] = CALLS.get("flaky", 0) + 1
    if CALLS["flaky"] < 2:
        raise RuntimeError("transient")
    ctx.progress(0.5, "halfway")
    return {"ok": True}


@job_handler("test_permanent")
def _perm(ctx: JobContext) -> dict[str, Any]:
    raise PermanentJobError("bad input")


def _status(job_id: str) -> Job:
    with session_scope() as db:
        j = db.get(Job, job_id)
        db.expunge(j)
        return j


def test_retry_then_success_records_attempts(client):
    with session_scope() as db:
        jid = queue.enqueue(db, "test_flaky", {}).id
    queue.run_job_inline(jid)
    j = _status(jid)
    assert j.status == "queued" and j.run_after is not None and "retrying" in j.message
    queue.run_job_inline(jid)
    j = _status(jid)
    assert j.status == "succeeded" and j.result == {"ok": True}
    r = client.get(f"/api/jobs/{jid}").json()
    assert [a["status"] for a in r["attempt_log"]] == ["failed", "succeeded"]


def test_permanent_failure_and_manual_retry(client):
    with session_scope() as db:
        jid = queue.enqueue(db, "test_permanent", {}).id
    queue.run_job_inline(jid)
    assert _status(jid).status == "failed"
    assert client.post(f"/api/jobs/{jid}/retry").status_code == 200
    assert _status(jid).status == "queued"
    assert client.post(f"/api/jobs/{jid}/cancel").status_code == 200
    assert _status(jid).status == "cancelled"
    assert client.post(f"/api/jobs/{jid}/cancel").status_code == 409


def test_recovery_requeues_interrupted_jobs(client):
    with session_scope() as db:
        j = queue.enqueue(db, "test_permanent", {})
        j.status = "running"
        jid = j.id
    assert queue.recover_stale_jobs() >= 1
    assert _status(jid).status == "queued"
    with session_scope() as db:
        queue.cancel(db, jid)


def test_idempotency_key_dedupes(client):
    with session_scope() as db:
        a = queue.enqueue(db, "test_permanent", {}, idempotency_key="same-key")
        b = queue.enqueue(db, "test_permanent", {}, idempotency_key="same-key")
        assert a.id == b.id
        queue.cancel(db, a.id)
