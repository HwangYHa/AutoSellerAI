from __future__ import annotations

import os
from pathlib import Path

from app.config import get_settings


def test_pytest_never_uses_normal_local_or_configured_production_database():
    settings = get_settings()
    project_root = Path(__file__).resolve().parents[1]
    normal_local_db = (project_root / "data" / "autoseller.db").resolve()
    active_test_db = Path(settings.db_path).resolve()

    assert active_test_db != normal_local_db
    assert os.environ.get("DATABASE_URL") == ""
    assert str(settings.database_url or "") == ""
    assert settings.env == "test"


def test_pytest_forces_dangerous_automation_off():
    settings = get_settings()
    assert settings.fulfillment_auto_purchase_enabled is False
    assert settings.inventory_auto_visibility_enabled is False
    assert settings.inquiry_auto_answer_enabled is False
    assert settings.image_ai_auto_generate is False
