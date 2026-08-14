"""Unified connection registry for Seller OS settings.

Dedicated supplier/channel pages may remain for diagnostics during migration, but
normal operation consumes this single registry.
"""
from __future__ import annotations

from typing import Any

from app.config import get_settings


def _commerce_secret_valid(value: str) -> bool:
    secret = (value or "").strip().strip('"').strip("'")
    if secret.startswith("$$"):
        secret = secret.replace("$$", "$")
    return len(secret) == 29 and secret.startswith(("$2a$", "$2b$", "$2y$"))


def get_connections() -> list[dict[str, Any]]:
    s = get_settings()
    return [
        {
            "code": "coupang",
            "name": "쿠팡",
            "kind": "판매채널",
            "configured": bool(s.coupang_access_key and s.coupang_secret_key and s.coupang_vendor_id),
            "capabilities": ["catalog_read", "order_read", "listing_write", "tracking_write"],
        },
        {
            "code": "smartstore",
            "name": "네이버 스마트스토어",
            "kind": "판매채널",
            "configured": bool(s.naver_client_id and _commerce_secret_valid(s.naver_client_secret)),
            "capabilities": ["catalog_read", "order_read", "listing_write", "tracking_write"],
        },
        {
            "code": "ownerclan",
            "name": "오너클랜",
            "kind": "공급처",
            "configured": bool(s.ownerclan_username and s.ownerclan_password),
            "capabilities": ["detail_read", "order_read", "order_write", "cancel_write"],
        },
        {
            "code": "domeggook",
            "name": "도매꾹",
            "kind": "공급처",
            "configured": bool(s.domeggook_api_key),
            "capabilities": ["search", "detail_read"],
        },
        {
            "code": "domemai",
            "name": "도매매",
            "kind": "공급처",
            "configured": bool(s.domemai_api_key),
            "capabilities": ["search", "detail_read"],
        },
        {
            "code": "onchannel",
            "name": "온채널",
            "kind": "공급처",
            "configured": bool(s.onchannel_login_id and s.onchannel_login_pw),
            "capabilities": ["search", "detail_read", "approval"],
        },
        {
            "code": "claude",
            "name": "Claude",
            "kind": "AI",
            "configured": bool(s.claude_api_key),
            "capabilities": ["text_generation", "scoring"],
        },
        {
            "code": "openai",
            "name": "OpenAI",
            "kind": "AI",
            "configured": bool(s.openai_api_key),
            "capabilities": ["image_generation"],
        },
        {
            "code": "redis",
            "name": "Redis / RQ",
            "kind": "인프라",
            "configured": bool(s.redis_url),
            "capabilities": ["background_jobs"],
        },
    ]


def get_connection_summary() -> dict[str, Any]:
    rows = get_connections()
    sales = [x for x in rows if x["kind"] == "판매채널"]
    suppliers = [x for x in rows if x["kind"] == "공급처"]
    return {
        "rows": rows,
        "sales_ready": any(x["configured"] for x in sales),
        "supplier_ready": any(x["configured"] for x in suppliers),
        "configured": sum(1 for x in rows if x["configured"]),
        "total": len(rows),
    }
