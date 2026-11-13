"""Structured (key=value) logging to console and a rotating file in data/logs."""
from __future__ import annotations

import logging
import logging.handlers

from app.config import get_settings

_configured = False


class _RedactFilter(logging.Filter):
    """Last line of defense: strip anything that looks like a provider key from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        s = get_settings()
        msg = record.getMessage()
        for secret in (s.gemini_api_key, s.groq_api_key, s.openrouter_api_key, s.mistral_api_key,
                       s.cloudflare_api_token, s.access_token):
            if secret and secret in msg:
                record.msg, record.args = msg.replace(secret, "***"), ()
                msg = record.msg
        return True


def configure_logging() -> None:
    global _configured
    if _configured:
        return
    s = get_settings()
    log_dir = s.data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("ts=%(asctime)s level=%(levelname)s logger=%(name)s msg=\"%(message)s\"")
    root = logging.getLogger("shelfcraft")
    root.setLevel(logging.INFO)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    file = logging.handlers.RotatingFileHandler(log_dir / "backend.log", maxBytes=5_000_000, backupCount=3,
                                                encoding="utf-8")
    file.setFormatter(fmt)
    for h in (console, file):
        h.addFilter(_RedactFilter())
        root.addHandler(h)
    root.propagate = False
    _configured = True
