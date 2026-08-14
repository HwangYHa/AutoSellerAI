"""Commercial fact verification state for supplier offers."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class OSOfferVerification(Base):
    __tablename__ = "os_offer_verifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    offer_id: Mapped[int] = mapped_column(
        ForeignKey("os_supplier_offers.id", ondelete="CASCADE"), unique=True, index=True
    )
    price_known: Mapped[bool] = mapped_column(Boolean, default=False)
    shipping_fee_known: Mapped[bool] = mapped_column(Boolean, default=False)
    stock_known: Mapped[bool] = mapped_column(Boolean, default=False)
    moq_known: Mapped[bool] = mapped_column(Boolean, default=False)
    variant_identity_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    online_sale_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    authenticity_evidence_available: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_source: Mapped[str] = mapped_column(String(80), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def dropship_order_ready(self) -> bool:
        return all((
            self.price_known,
            self.shipping_fee_known,
            self.stock_known,
            self.moq_known,
            self.variant_identity_verified,
        ))
