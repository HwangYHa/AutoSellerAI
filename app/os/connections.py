"""Unified connection registry for Seller OS settings.

Authentication/read capability and verified automatic ordering are intentionally
separate. A supplier is not considered safe for auto-order merely because login
credentials exist.
"""
from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.os.drivers import supplier_driver_status


def _commerce_secret_valid(value: str) -> bool:
    secret = (value or "").strip().strip('"').strip("'")
    if secret.startswith("$$"):
        secret = secret.replace("$$", "$")
    return len(secret) == 29 and secret.startswith(("$2a$", "$2b$", "$2y$"))


def _supplier_row(code: str, name: str, configured: bool, capabilities: list[str]) -> dict[str, Any]:
    driver = supplier_driver_status(code)
    return {
        "code": code,
        "name": name,
        "kind": "공급처",
        "configured": configured,
        "capabilities": capabilities,
        "auto_order_verified": bool(driver.get("can_create_order")),
        "driver_note": driver.get("note", ""),
    }


def get_connections() -> list[dict[str, Any]]:
    s = get_settings()
    return [
        {
            "code": "coupang",
            "name": "쿠팡",
            "kind": "판매채널",
            "configured": bool(s.coupang_access_key and s.coupang_secret_key and s.coupang_vendor_id),
            "capabilities": ["catalog_read", "order_read", "listing_write", "tracking_write"],
            "auto_order_verified": None,
            "driver_note": "",
        },
        {
            "code": "smartstore",
            "name": "네이버 스마트스토어",
            "kind": "판매채널",
            "configured": bool(s.naver_client_id and _commerce_secret_valid(s.naver_client_secret)),
            "capabilities": ["catalog_read", "order_read", "listing_write", "tracking_write"],
            "auto_order_verified": None,
            "driver_note": "",
        },
        _supplier_row(
            "ownerclan",
            "오너클랜",
            bool(s.ownerclan_username and s.ownerclan_password),
            ["detail_read", "order_read", "legacy_order_api"],
        ),
        _supplier_row(
            "domeggook",
            "도매꾹",
            bool(s.domeggook_api_key),
            ["search", "detail_read"],
        ),
        _supplier_row(
            "domemai",
            "도매매",
            bool(s.domemai_api_key),
            ["search", "detail_read"],
        ),
        _supplier_row(
            "onchannel",
            "온채널",
            bool(s.onchannel_login_id and s.onchannel_login_pw),
            ["search", "detail_read", "approval"],
        ),
        {
            "code": "claude",
            "name": "Claude",
            "kind": "AI",
            "configured": bool(s.claude_api_key),
            "capabilities": ["text_generation", "scoring"],
            "auto_order_verified": None,
            "driver_note": "",
        },
        {
            "code": "openai",
            "name": "OpenAI",
            "kind": "AI",
            "configured": bool(s.openai_api_key),
            "capabilities": ["image_generation"],
            "auto_order_verified": None,
            "driver_note": "",
        },
        {
            "code": "redis",
            "name": "Redis / RQ",
            "kind": "인프라",
            "configured": bool(s.redis_url),
            "capabilities": ["background_jobs"],
            "auto_order_verified": None,
            "driver_note": "",
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
        "verified_auto_order_suppliers": sum(1 for x in suppliers if x["auto_order_verified"]),
        "configured": sum(1 for x in rows if x["configured"]),
        "total": len(rows),
    }
