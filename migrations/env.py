from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import get_settings
from app.db import Base
import app.os.models  # noqa: F401  # register Seller OS tables

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
url = str(getattr(settings, "database_url", "") or "").strip()
if not url:
    db_path = str(settings.db_path).replace("\\", "/")
    url = f"sqlite:///{db_path}"
config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))

target_metadata = Base.metadata


def include_object(object_, name, type_, reflected, compare_to):  # noqa: ARG001
    # v3 migration ownership is intentionally limited to canonical os_* tables.
    # Legacy tables are transitional infrastructure and are not rewritten by v3.
    if type_ == "table":
        return name.startswith("os_") or name == "alembic_version"
    table = getattr(object_, "table", None)
    if table is not None:
        return table.name.startswith("os_")
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=include_object,
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
