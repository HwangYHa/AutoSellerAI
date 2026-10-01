from __future__ import annotations

import app.db as db_module


def test_primary_database_engine_prefers_database_url(monkeypatch):
    class Settings:
        database_url = "postgresql+psycopg://example/db"
        db_path = "data/ignored.db"

    monkeypatch.setattr(db_module, "get_settings", lambda: Settings())
    assert db_module._database_url() == Settings.database_url


def test_primary_database_engine_falls_back_to_sqlite_path(monkeypatch):
    class Settings:
        database_url = ""
        db_path = "data/autoseller.db"

    monkeypatch.setattr(db_module, "get_settings", lambda: Settings())
    assert db_module._database_url() == "sqlite:///data/autoseller.db"
