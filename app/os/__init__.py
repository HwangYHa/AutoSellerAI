"""Seller OS v3 operating kernel.

The OS package is the canonical application layer for AutoSellerAI.
Legacy modules remain infrastructure/compatibility code until their callers are migrated.
"""

from app.os.schema import ensure_os_schema

__all__ = ["ensure_os_schema"]
