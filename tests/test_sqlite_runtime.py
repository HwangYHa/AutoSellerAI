from __future__ import annotations

import threading
import time

from sqlalchemy import Integer, String, create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.sqlite_runtime import is_sqlite_contention_error


class _Base(DeclarativeBase):
    pass


class _Row(_Base):
    __tablename__ = "runtime_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    value: Mapped[str] = mapped_column(String(100))


def test_sqlite_connections_enable_busy_timeout_wal_and_foreign_keys(tmp_path):
    db_path = tmp_path / "runtime.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        busy_timeout = conn.exec_driver_sql("PRAGMA busy_timeout").scalar_one()
        journal_mode = str(conn.exec_driver_sql("PRAGMA journal_mode").scalar_one()).lower()
        foreign_keys = conn.exec_driver_sql("PRAGMA foreign_keys").scalar_one()
        synchronous = conn.exec_driver_sql("PRAGMA synchronous").scalar_one()

    assert busy_timeout == 30_000
    assert journal_mode == "wal"
    assert foreign_keys == 1
    assert synchronous == 1  # SQLite NORMAL


def test_only_transient_sqlite_contention_is_classified_for_retry():
    locked = OperationalError("INSERT", {}, Exception("database is locked"))
    busy = OperationalError("INSERT", {}, Exception("database is busy"))
    already_exists = OperationalError("CREATE", {}, Exception("table threads_posts already exists"))
    unrelated = OperationalError("SELECT", {}, Exception("no such table: missing"))

    assert is_sqlite_contention_error(locked)
    assert is_sqlite_contention_error(busy)
    assert is_sqlite_contention_error(already_exists)
    assert not is_sqlite_contention_error(unrelated)


def test_orm_writers_are_serialized_instead_of_raising_database_locked(tmp_path):
    db_path = tmp_path / "writers.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    _Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False)

    first_flushed = threading.Event()
    allow_first_commit = threading.Event()
    errors: list[BaseException] = []

    def first_writer() -> None:
        try:
            with SessionLocal() as db:
                db.add(_Row(value="first"))
                db.flush()  # acquires the global SQLite writer mutex
                first_flushed.set()
                assert allow_first_commit.wait(timeout=3)
                db.commit()
        except BaseException as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    second_done = threading.Event()

    def second_writer() -> None:
        try:
            assert first_flushed.wait(timeout=3)
            with SessionLocal() as db:
                db.add(_Row(value="second"))
                db.commit()  # must wait for first writer, not fail with SQLITE_BUSY
            second_done.set()
        except BaseException as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    t1 = threading.Thread(target=first_writer)
    t2 = threading.Thread(target=second_writer)
    t1.start()
    t2.start()

    assert first_flushed.wait(timeout=3)
    time.sleep(0.1)
    assert not second_done.is_set()

    allow_first_commit.set()
    t1.join(timeout=3)
    t2.join(timeout=3)

    assert not errors
    assert second_done.is_set()

    with SessionLocal() as db:
        values = [row.value for row in db.query(_Row).order_by(_Row.id).all()]
    assert values == ["first", "second"]
