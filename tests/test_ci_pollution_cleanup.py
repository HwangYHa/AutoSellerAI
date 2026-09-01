from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base, Product
from scripts import cleanup_ci_test_pollution as cleanup_mod


def test_cleanup_removes_only_known_ci_product(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'cleanup.db'}")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        db.add_all(
            [
                Product(
                    sku="CI-PROFIT-LEGACY-1",
                    source="ci",
                    source_id="ci-legacy-1",
                    name="CI 차량용 청소기",
                    supply_price=10000,
                    sell_price=15000,
                ),
                Product(
                    sku="REAL-VEHICLE-VACUUM-1",
                    source="onchannel",
                    source_id="real-1",
                    name="차량용 청소기",
                    supply_price=12000,
                    sell_price=19000,
                ),
            ]
        )
        db.commit()

    monkeypatch.setattr(cleanup_mod, "_get_engine", lambda: engine)

    preview = cleanup_mod.cleanup(apply=False)
    assert preview["matched"].get("products") == 1

    result = cleanup_mod.cleanup(apply=True)
    assert result["deleted"].get("products") == 1

    with Session(engine) as db:
        remaining = list(db.scalars(select(Product).order_by(Product.id)).all())
    assert [row.sku for row in remaining] == ["REAL-VEHICLE-VACUUM-1"]


def test_local_deploy_runs_ci_cleanup_before_services_start():
    script = Path("scripts/deploy_local.ps1").read_text(encoding="utf-8")
    cleanup_cmd = "docker compose run --rm --no-deps autoseller python scripts/cleanup_ci_test_pollution.py --apply"
    start_cmd = "docker compose up -d --force-recreate"

    assert cleanup_cmd in script
    assert start_cmd in script
    assert script.index(cleanup_cmd) < script.index(start_cmd)
