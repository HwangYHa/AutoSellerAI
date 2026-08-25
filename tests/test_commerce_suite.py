from app.os.commerce_ops_models import OSChannelTemplate, OSInventoryPolicy, OSOrderWorkMeta


def test_commerce_suite_uses_additive_extension_tables():
    assert OSOrderWorkMeta.__tablename__ == "os_order_work_meta"
    assert OSInventoryPolicy.__tablename__ == "os_inventory_policies"
    assert OSChannelTemplate.__tablename__ == "os_channel_templates"


def test_inventory_policy_has_safety_controls():
    columns = OSInventoryPolicy.__table__.columns
    assert "safety_stock" in columns
    assert "reserved_qty" in columns
    assert "auto_soldout" in columns
    assert "sellable" in columns


def test_order_work_meta_has_operational_fields():
    columns = OSOrderWorkMeta.__table__.columns
    for name in ("user_tag", "owner", "priority", "cs_memo", "gift_note", "checked"):
        assert name in columns
