"""First-run setup: migrations, default user/settings, provider rows, built-in templates."""
from __future__ import annotations

import logging

from alembic import command
from alembic.config import Config

from app.ai.provider_registry import ensure_rows
from app.config import BACKEND_DIR, get_settings
from app.db.models import User, UserSettings
from app.db.session import get_engine, session_scope

log = logging.getLogger("shelfcraft.bootstrap")


def run_migrations(url: str | None = None) -> None:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    # configparser treats '%' as interpolation; URL-encoded Windows paths (C%3A) must be escaped.
    cfg.set_main_option("sqlalchemy.url", (url or get_settings().sqlalchemy_url).replace("%", "%%"))
    command.upgrade(cfg, "head")


def bootstrap() -> None:
    get_settings().ensure_dirs()
    run_migrations(get_engine().url.render_as_string(hide_password=False))
    with session_scope() as db:
        user = db.query(User).first()
        if user is None:
            user = User(display_name="You")
            db.add(user)
            db.flush()
        if db.query(UserSettings).first() is None:
            db.add(UserSettings(user_id=user.id, fallback_order=["gemini", "groq", "openrouter", "cloudflare"],
                                generation_defaults={"aspect": "1:1", "image_size": 1024, "language": "en"}))
        ensure_rows(db)
    from app.services.templates import seed_builtin_templates

    with session_scope() as db:
        seed_builtin_templates(db)
    log.info("bootstrap complete")
