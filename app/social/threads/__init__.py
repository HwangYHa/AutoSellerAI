"""Threads social-commerce domain."""

from app.social.threads import models as models  # noqa: F401
from app.social.threads import growth_models as growth_models  # noqa: F401
from app.social.threads import auth_models as auth_models  # noqa: F401
from app.social.threads.migrations import ensure_threads_schema

ensure_threads_schema()

__all__ = ["models", "growth_models", "auth_models"]
