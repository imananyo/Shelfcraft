"""FastAPI application factory."""
from __future__ import annotations

import logging
import secrets
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.ai.base import NoProviderAvailable, ProviderError
from app.config import get_settings
from app.logging_setup import configure_logging
from app.services.assets import UploadRejected
from app.storage.local import StorageError

log = logging.getLogger("shelfcraft")


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201
    from app.bootstrap import bootstrap
    from app.jobs import handlers  # noqa: F401 - registers job handlers
    from app.jobs.queue import start_workers, stop_workers

    bootstrap()
    if app.state.start_workers:
        start_workers()
    log.info("Shelfcraft API ready")
    yield
    if app.state.start_workers:
        stop_workers()
    log.info("Shelfcraft API stopped")


def create_app(*, start_workers: bool = True) -> FastAPI:
    settings = get_settings()
    configure_logging()
    settings.ensure_dirs()
    app = FastAPI(title="Shelfcraft API", version="0.1.0", lifespan=lifespan)
    app.state.start_workers = start_workers

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin, "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def access_guard(request: Request, call_next):  # noqa: ANN001, ANN202
        token = get_settings().access_token
        path = request.url.path
        if token and path.startswith("/api") and path != "/api/health":
            supplied = request.headers.get("x-shelfcraft-token") or request.cookies.get("shelfcraft_token") or ""
            if not secrets.compare_digest(supplied, token):
                return JSONResponse({"detail": "Access token required"}, status_code=401)
        t0 = time.perf_counter()
        response = await call_next(request)
        if path.startswith("/api") and not path.endswith(("/file", "/thumb")):
            log.info("%s %s %d %.0fms", request.method, path, response.status_code,
                     (time.perf_counter() - t0) * 1000)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    _register_error_handlers(app)
    _register_routers(app)
    return app


def _error(status: int, code: str, message: str, **extra: Any) -> JSONResponse:
    return JSONResponse({"detail": message, "code": code, **extra}, status_code=status)


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(UploadRejected)
    async def _upload(_r: Request, e: UploadRejected) -> JSONResponse:
        return _error(422, "upload_rejected", str(e))

    @app.exception_handler(StorageError)
    async def _storage(_r: Request, e: StorageError) -> JSONResponse:
        return _error(400, "storage_error", str(e))

    @app.exception_handler(NoProviderAvailable)
    async def _no_provider(_r: Request, e: NoProviderAvailable) -> JSONResponse:
        return _error(503, "no_provider", str(e), attempts=e.attempts, kind=e.kind)

    @app.exception_handler(ProviderError)
    async def _provider(_r: Request, e: ProviderError) -> JSONResponse:
        return _error(502, "provider_error", e.message, provider=e.provider)

    @app.exception_handler(RequestValidationError)
    async def _validation(_r: Request, e: RequestValidationError) -> JSONResponse:
        errors = [{"loc": list(err.get("loc", [])), "msg": err.get("msg")} for err in e.errors()]
        first = errors[0] if errors else {"loc": [], "msg": "invalid request"}
        field = ".".join(str(p) for p in first["loc"] if p != "body")
        return _error(422, "validation_error", f"{field}: {first['msg']}" if field else first["msg"], errors=errors)

    @app.exception_handler(Exception)
    async def _unhandled(r: Request, e: Exception) -> JSONResponse:
        log.exception("unhandled error on %s %s", r.method, r.url.path)
        return _error(500, "internal_error", "Something went wrong on the server. Details are in the backend log.")


def _register_routers(app: FastAPI) -> None:
    from app.routers import ROUTERS

    for router in ROUTERS:
        app.include_router(router, prefix="/api")


app = create_app()
