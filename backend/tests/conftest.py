"""Test fixtures: every test session gets an isolated data dir + SQLite DB; hosted providers are
never configured (env keys blanked), so tests cannot make network calls to paid or free APIs."""
from __future__ import annotations

import io
import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="shelfcraft-test-"))
os.environ["SHELFCRAFT_DATA_DIR"] = str(_TMP)
os.environ.pop("SHELFCRAFT_DATABASE_URL", None)
os.environ.pop("SHELFCRAFT_ACCESS_TOKEN", None)
for k in ("GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY", "MISTRAL_API_KEY", "CLOUDFLARE_API_TOKEN",
          "CLOUDFLARE_ACCOUNT_ID"):
    os.environ[k] = ""
# Point Ollama at a closed port so tests never depend on (or wait for) a local model.
os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:9"

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    from app.db.session import init_engine
    from app.main import create_app
    from app.storage.local import reset_storage

    init_engine(get_settings().sqlalchemy_url)
    reset_storage(get_settings().media_dir)
    app = create_app(start_workers=False)  # tests run jobs inline for determinism
    with TestClient(app) as c:
        # Local diffusion would take minutes on CPU — disable it for the test session.
        c.patch("/api/providers/local_diffusion", json={"enabled": False})
        yield c
    shutil.rmtree(_TMP, ignore_errors=True)


def make_png(w: int = 400, h: int = 300, color: str = "#2a9d8f", with_object: bool = True) -> bytes:
    """Synthetic product photo: colored rounded object on a light background."""
    im = Image.new("RGB", (w, h), "#f2efe9")
    d = ImageDraw.Draw(im)
    if with_object:
        d.rounded_rectangle((w * 0.3, h * 0.2, w * 0.7, h * 0.85), radius=24, fill=color)
        d.ellipse((w * 0.42, h * 0.32, w * 0.58, h * 0.48), fill="#ffffff")
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def png_bytes() -> bytes:
    return make_png()


def run_pending_jobs() -> list[str]:
    """Run every queued job synchronously; returns their final statuses."""
    from sqlalchemy import select

    from app.db.models import Job
    from app.db.session import session_scope
    from app.jobs.queue import run_job_inline

    statuses = []
    for _ in range(50):
        with session_scope() as db:
            job_id = db.scalar(select(Job.id).where(Job.status == "queued").order_by(Job.created_at).limit(1))
        if job_id is None:
            break
        run_job_inline(job_id)
        with session_scope() as db:
            statuses.append(db.get(Job, job_id).status)
    return statuses
