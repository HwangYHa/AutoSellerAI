from __future__ import annotations

import inspect

from app.os import commerce_automation
from app.os.bulk_market_tools import BULK_COLUMNS
from app.os.channel_template_runtime import install_channel_template_runtime
from app.os.commerce_automation_models import (
    OSChannelSettlement,
    OSInventoryAutomationState,
    OSMarketplaceInquiry,
    OSPaymentSession,
    OSSchedulerRule,
)
from app.os.scheduler import DEFAULT_JOBS
from app.os.tasks import TASK_TIMEOUT_SECONDS


def test_full_commerce_automation_tables_are_additive_os_tables():
    names = {
        OSMarketplaceInquiry.__tablename__,
        OSChannelSettlement.__tablename__,
        OSInventoryAutomationState.__tablename__,
        OSPaymentSession.__tablename__,
        OSSchedulerRule.__tablename__,
    }
    assert names == {
        "os_marketplace_inquiries",
        "os_channel_settlements",
        "os_inventory_automation_states",
        "os_payment_sessions",
        "os_scheduler_rules",
    }


def test_scheduler_covers_requested_commerce_cycles():
    expected = {
        "order_sync",
        "claim_sync",
        "inquiry_sync",
        "inventory_automation",
        "settlement_sync",
        "payment_sync",
        "fulfillment_cycle",
    }
    assert expected <= set(DEFAULT_JOBS)
    assert expected <= set(TASK_TIMEOUT_SECONDS)
    assert DEFAULT_JOBS["claim_sync"]["default_minutes"] == 1
    assert DEFAULT_JOBS["payment_sync"]["default_minutes"] == 1


def test_inventory_automation_has_hysteresis_and_unknown_stock_guard():
    source = inspect.getsource(commerce_automation.run_inventory_automation)
    assert "confirmations_required = max(2" in source
    assert "if stock is None" in source
    assert "state.auto_sold_out" in source
    assert "set_coupang_listing_stock" in source
    assert "change_naver_sale_status" in source


def test_inquiry_sync_includes_product_and_customer_inquiries():
    source = inspect.getsource(commerce_automation.sync_inquiries)
    assert "collect_coupang_inquiries" in source
    assert "collect_naver_inquiries" in source
    assert "collect_naver_customer_inquiries" in source


def test_channel_settlement_promotes_to_canonical_profit_ledger():
    source = inspect.getsource(commerce_automation.sync_settlements)
    assert "reconcile_channel_settlements" in source


def test_bulk_sheet_contract_is_stable():
    assert "product_id" in BULK_COLUMNS
    assert "sku" in BULK_COLUMNS
    assert "sell_price" in BULK_COLUMNS
    assert "options_json" in BULK_COLUMNS


def test_channel_template_runtime_is_idempotently_installable():
    install_channel_template_runtime()
    install_channel_template_runtime()
    from app.platforms.coupang import CoupangUploader
    from app.platforms.smartstore import SmartStoreUploader
    assert getattr(CoupangUploader.create_product, "_autoseller_template_wrapped", False)
    assert getattr(SmartStoreUploader.create_product, "_autoseller_template_wrapped", False)


def test_supplier_order_executor_rechecks_claim_hold_before_side_effect():
    from app.os import fulfillment_executor
    source = inspect.getsource(fulfillment_executor.execute_supplier_order)
    assert "ORDER_BLOCKED_BY_CLAIM_OR_HOLD" in source
    assert "immediately before the first supplier side" in source
