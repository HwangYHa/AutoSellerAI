from __future__ import annotations

from sqlalchemy import inspect, text

from app.db import _get_engine, init_db


def ensure_threads_schema() -> None:
    """Apply additive SQLite-safe migrations for Threads extensions.

    AutoSellerAI currently uses create_all() without Alembic. create_all() creates
    new tables but does not add columns to an existing table, so we explicitly
    add only backward-compatible nullable/defaulted columns here.
    """
    init_db()
    engine = _get_engine()
    inspector = inspect(engine)
    if "scheduled_social_posts" not in inspector.get_table_names():
        return

    existing = {c["name"] for c in inspector.get_columns("scheduled_social_posts")}
    additions = {
        "media_type": "VARCHAR(20) NOT NULL DEFAULT 'TEXT'",
        "media_url": "TEXT NOT NULL DEFAULT ''",
        "alt_text": "VARCHAR(1000) NOT NULL DEFAULT ''",
        "carousel_items_json": "TEXT NOT NULL DEFAULT '[]'",
    }
    with engine.begin() as conn:
        for name, ddl in additions.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE scheduled_social_posts ADD COLUMN {name} {ddl}"))
