"""Seller OS v3 canonical schema

Revision ID: 20260814_0001
Revises: None
Create Date: 2026-08-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260814_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "os_suppliers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("capabilities_json", sa.Text(), nullable=False),
        sa.Column("connection_status", sa.String(30), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("code", name="uq_os_suppliers_code"),
    )
    op.create_index("ix_os_suppliers_code", "os_suppliers", ["code"])
    op.create_index("ix_os_suppliers_enabled", "os_suppliers", ["enabled"])
    op.create_index("ix_os_suppliers_connection_status", "os_suppliers", ["connection_status"])

    op.create_table(
        "os_products",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("sku", sa.String(140), nullable=False),
        sa.Column("name", sa.String(400), nullable=False),
        sa.Column("brand", sa.String(160), nullable=False),
        sa.Column("category", sa.String(240), nullable=False),
        sa.Column("origin", sa.String(120), nullable=False),
        sa.Column("material", sa.String(240), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("product_type", sa.String(30), nullable=False),
        sa.Column("content_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("sku", name="uq_os_products_sku"),
    )
    for name in ("sku", "brand", "category", "status", "product_type"):
        op.create_index(f"ix_os_products_{name}", "os_products", [name])

    op.create_table(
        "os_product_variants",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("os_products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sku", sa.String(180), nullable=False),
        sa.Column("option_key", sa.String(300), nullable=False),
        sa.Column("option_json", sa.Text(), nullable=False),
        sa.Column("barcode", sa.String(100), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("sku", name="uq_os_product_variants_sku"),
        sa.UniqueConstraint("product_id", "option_key", name="uq_os_variant_product_option"),
    )
    for name in ("product_id", "sku", "barcode", "status"):
        op.create_index(f"ix_os_product_variants_{name}", "os_product_variants", [name])

    op.create_table(
        "os_supplier_offers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("os_suppliers.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("os_products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variant_id", sa.Integer(), sa.ForeignKey("os_product_variants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("supplier_product_id", sa.String(220), nullable=False),
        sa.Column("supplier_variant_id", sa.String(220), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("supply_price_krw", sa.Integer(), nullable=False),
        sa.Column("shipping_fee_krw", sa.Integer(), nullable=False),
        sa.Column("stock_qty", sa.Integer(), nullable=True),
        sa.Column("moq", sa.Integer(), nullable=False),
        sa.Column("lead_time_days", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("raw_json", sa.Text(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("supplier_id", "supplier_product_id", "supplier_variant_id", name="uq_os_supplier_offer_identity"),
    )
    for name in ("supplier_id", "product_id", "variant_id", "supplier_product_id", "supplier_variant_id", "status", "last_synced_at"):
        op.create_index(f"ix_os_supplier_offers_{name}", "os_supplier_offers", [name])
    op.create_index("ix_os_offer_product_status", "os_supplier_offers", ["product_id", "status"])

    op.create_table(
        "os_listings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("os_products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform", sa.String(40), nullable=False),
        sa.Column("account_key", sa.String(80), nullable=False),
        sa.Column("external_product_id", sa.String(220), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("sale_price_krw", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("product_id", "platform", "account_key", name="uq_os_listing_product_platform"),
        sa.UniqueConstraint("platform", "account_key", "external_product_id", name="uq_os_listing_external"),
    )
    for name in ("product_id", "platform", "account_key", "external_product_id", "status"):
        op.create_index(f"ix_os_listings_{name}", "os_listings", [name])

    op.create_table(
        "os_listing_variants",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("listing_id", sa.Integer(), sa.ForeignKey("os_listings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variant_id", sa.Integer(), sa.ForeignKey("os_product_variants.id", ondelete="SET NULL"), nullable=True),
        sa.Column("external_item_id", sa.String(220), nullable=False),
        sa.Column("external_parent_item_id", sa.String(220), nullable=False),
        sa.Column("sale_price_krw", sa.Integer(), nullable=False),
        sa.Column("stock_qty", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("listing_id", "external_item_id", name="uq_os_listing_variant_external"),
    )
    for name in ("listing_id", "variant_id", "external_item_id", "external_parent_item_id", "status"):
        op.create_index(f"ix_os_listing_variants_{name}", "os_listing_variants", [name])

    op.create_table(
        "os_sales_orders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("platform", sa.String(40), nullable=False),
        sa.Column("account_key", sa.String(80), nullable=False),
        sa.Column("external_order_id", sa.String(220), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("buyer_name", sa.String(120), nullable=False),
        sa.Column("receiver_name", sa.String(120), nullable=False),
        sa.Column("receiver_phone", sa.String(80), nullable=False),
        sa.Column("shipping_address", sa.Text(), nullable=False),
        sa.Column("shipping_message", sa.String(400), nullable=False),
        sa.Column("ordered_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("platform", "account_key", "external_order_id", name="uq_os_sales_order_external"),
    )
    for name in ("platform", "account_key", "external_order_id", "status", "ordered_at"):
        op.create_index(f"ix_os_sales_orders_{name}", "os_sales_orders", [name])

    op.create_table(
        "os_sales_order_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("os_sales_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_item_id", sa.String(220), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("os_products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("variant_id", sa.Integer(), sa.ForeignKey("os_product_variants.id", ondelete="SET NULL"), nullable=True),
        sa.Column("listing_id", sa.Integer(), sa.ForeignKey("os_listings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("supplier_offer_id", sa.Integer(), sa.ForeignKey("os_supplier_offers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("product_name", sa.String(400), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_sale_price_krw", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("exception_code", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("order_id", "external_item_id", name="uq_os_order_item_external"),
    )
    for name in ("order_id", "external_item_id", "product_id", "variant_id", "listing_id", "supplier_offer_id", "status", "exception_code"):
        op.create_index(f"ix_os_sales_order_items_{name}", "os_sales_order_items", [name])

    op.create_table(
        "os_approval_requests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("action_type", sa.String(80), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.String(120), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("summary", sa.String(500), nullable=False),
        sa.Column("risk_level", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("requested_by", sa.String(120), nullable=False),
        sa.Column("decided_by", sa.String(120), nullable=False),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
    )
    for name in ("action_type", "entity_type", "entity_id", "payload_hash", "risk_level", "status", "requested_at", "expires_at"):
        op.create_index(f"ix_os_approval_requests_{name}", "os_approval_requests", [name])
    op.create_index("ix_os_approval_pending", "os_approval_requests", ["status", "risk_level", "requested_at"])

    op.create_table(
        "os_operation_executions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("action_type", sa.String(80), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.String(120), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("approval_id", sa.Integer(), sa.ForeignKey("os_approval_requests.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("request_json", sa.Text(), nullable=False),
        sa.Column("response_json", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_os_operation_executions_idempotency_key"),
    )
    for name in ("action_type", "entity_type", "entity_id", "idempotency_key", "approval_id", "status", "created_at"):
        op.create_index(f"ix_os_operation_executions_{name}", "os_operation_executions", [name])

    op.create_table(
        "os_fulfillments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("order_item_id", sa.Integer(), sa.ForeignKey("os_sales_order_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("supplier_offer_id", sa.Integer(), sa.ForeignKey("os_supplier_offers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("supplier_code", sa.String(50), nullable=False),
        sa.Column("supplier_order_id", sa.String(220), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("supply_cost_krw", sa.Integer(), nullable=False),
        sa.Column("shipping_cost_krw", sa.Integer(), nullable=False),
        sa.Column("delivery_company", sa.String(80), nullable=False),
        sa.Column("tracking_number", sa.String(140), nullable=False),
        sa.Column("invoice_registered", sa.Boolean(), nullable=False),
        sa.Column("failure_code", sa.String(80), nullable=False),
        sa.Column("failure_message", sa.Text(), nullable=False),
        sa.Column("ordered_at", sa.DateTime(), nullable=True),
        sa.Column("shipped_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("order_item_id", name="uq_os_fulfillments_order_item_id"),
    )
    for name in ("order_item_id", "supplier_offer_id", "supplier_code", "supplier_order_id", "status", "tracking_number", "invoice_registered", "failure_code"):
        op.create_index(f"ix_os_fulfillments_{name}", "os_fulfillments", [name])

    op.create_table(
        "os_settlement_lines",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("order_item_id", sa.Integer(), sa.ForeignKey("os_sales_order_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform", sa.String(40), nullable=False),
        sa.Column("gross_revenue_krw", sa.Integer(), nullable=False),
        sa.Column("supply_cost_krw", sa.Integer(), nullable=False),
        sa.Column("platform_fee_krw", sa.Integer(), nullable=False),
        sa.Column("shipping_cost_krw", sa.Integer(), nullable=False),
        sa.Column("ad_cost_krw", sa.Integer(), nullable=False),
        sa.Column("return_cost_krw", sa.Integer(), nullable=False),
        sa.Column("tax_cost_krw", sa.Integer(), nullable=False),
        sa.Column("net_profit_krw", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("settled_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("order_item_id", name="uq_os_settlement_lines_order_item_id"),
    )
    for name in ("order_item_id", "platform", "net_profit_krw", "status", "settled_at"):
        op.create_index(f"ix_os_settlement_lines_{name}", "os_settlement_lines", [name])

    op.create_table(
        "os_learning_signals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("os_products.id", ondelete="CASCADE"), nullable=True),
        sa.Column("variant_id", sa.Integer(), sa.ForeignKey("os_product_variants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("listing_id", sa.Integer(), sa.ForeignKey("os_listings.id", ondelete="CASCADE"), nullable=True),
        sa.Column("signal_type", sa.String(80), nullable=False),
        sa.Column("value_int", sa.Integer(), nullable=False),
        sa.Column("context_json", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
    )
    for name in ("product_id", "variant_id", "listing_id", "signal_type", "observed_at"):
        op.create_index(f"ix_os_learning_signals_{name}", "os_learning_signals", [name])

    op.create_table(
        "os_background_tasks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_key", sa.String(160), nullable=False),
        sa.Column("task_type", sa.String(80), nullable=False),
        sa.Column("queue_name", sa.String(40), nullable=False),
        sa.Column("dedupe_key", sa.String(180), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("progress_pct", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("task_key", name="uq_os_background_tasks_task_key"),
    )
    for name in ("task_key", "task_type", "queue_name", "dedupe_key", "status", "created_at"):
        op.create_index(f"ix_os_background_tasks_{name}", "os_background_tasks", [name])

    op.create_table(
        "os_sync_cursors",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(60), nullable=False),
        sa.Column("scope", sa.String(100), nullable=False),
        sa.Column("cursor_value", sa.Text(), nullable=False),
        sa.Column("watermark", sa.String(120), nullable=False),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("source", "scope", name="uq_os_sync_cursor_source_scope"),
    )
    op.create_index("ix_os_sync_cursors_source", "os_sync_cursors", ["source"])
    op.create_index("ix_os_sync_cursors_scope", "os_sync_cursors", ["scope"])

    op.create_table(
        "os_audit_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("actor", sa.String(120), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.String(120), nullable=False),
        sa.Column("data_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    for name in ("actor", "action", "entity_type", "entity_id", "created_at"):
        op.create_index(f"ix_os_audit_events_{name}", "os_audit_events", [name])


def downgrade() -> None:
    for table in (
        "os_audit_events",
        "os_sync_cursors",
        "os_background_tasks",
        "os_learning_signals",
        "os_settlement_lines",
        "os_fulfillments",
        "os_operation_executions",
        "os_approval_requests",
        "os_sales_order_items",
        "os_sales_orders",
        "os_listing_variants",
        "os_listings",
        "os_supplier_offers",
        "os_product_variants",
        "os_products",
        "os_suppliers",
    ):
        op.drop_table(table)
