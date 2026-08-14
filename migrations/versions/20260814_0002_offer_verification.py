"""supplier offer commercial fact verification

Revision ID: 20260814_0002
Revises: 20260814_0001
Create Date: 2026-08-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260814_0002"
down_revision: Union[str, None] = "20260814_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "os_offer_verifications",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "offer_id",
            sa.Integer(),
            sa.ForeignKey("os_supplier_offers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("price_known", sa.Boolean(), nullable=False),
        sa.Column("shipping_fee_known", sa.Boolean(), nullable=False),
        sa.Column("stock_known", sa.Boolean(), nullable=False),
        sa.Column("moq_known", sa.Boolean(), nullable=False),
        sa.Column("variant_identity_verified", sa.Boolean(), nullable=False),
        sa.Column("online_sale_allowed", sa.Boolean(), nullable=False),
        sa.Column("authenticity_evidence_available", sa.Boolean(), nullable=False),
        sa.Column("verification_source", sa.String(80), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("offer_id", name="uq_os_offer_verifications_offer_id"),
    )
    op.create_index("ix_os_offer_verifications_offer_id", "os_offer_verifications", ["offer_id"])


def downgrade() -> None:
    op.drop_index("ix_os_offer_verifications_offer_id", table_name="os_offer_verifications")
    op.drop_table("os_offer_verifications")
