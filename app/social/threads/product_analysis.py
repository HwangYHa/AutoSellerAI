from __future__ import annotations

import ipaddress
import json
import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.db import Product, get_db


_MAX_DETAIL_TEXT = 12000
_MAX_REMOTE_TEXT = 8000
_MAX_OPTIONS = 80
_MAX_IMAGES = 20


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not value:
        return []
    try:
        parsed = json.loads(str(value))
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _clean_text(value: Any, limit: int) -> str:
    text = str(value or "")
    if not text:
        return ""
    if "<" in text and ">" in text:
        soup = BeautifulSoup(text, "lxml")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _safe_public_url(url: str) -> bool:
    try:
        parsed = urlparse(str(url or "").strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        host = parsed.hostname.lower()
        if host in {"localhost", "0.0.0.0", "::1"} or host.endswith(".local"):
            return False
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
        except ValueError:
            pass
        return True
    except Exception:
        return False


def _fetch_public_page_text(url: str) -> tuple[str, str]:
    enabled = str(os.getenv("THREADS_PRODUCT_PAGE_FETCH", "true")).strip().lower() in {"1", "true", "yes", "on"}
    if not enabled or not _safe_public_url(url):
        return "", "disabled_or_non_public"
    try:
        response = httpx.get(
            url,
            timeout=8.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; AutoSellerAI/1.0; product-analysis)",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "html" not in content_type.lower():
            return "", f"unsupported_content_type:{content_type[:60]}"
        return _clean_text(response.text, _MAX_REMOTE_TEXT), "ok"
    except Exception as exc:
        return "", f"fetch_failed:{type(exc).__name__}"


def _product_row(product_id: int) -> Product | None:
    with get_db() as db:
        return db.get(Product, int(product_id))


def build_product_evidence(product: dict[str, Any]) -> dict[str, Any]:
    """Build a fact-only evidence bundle for Threads content generation.

    Stored database facts are authoritative. The source page is only a best-effort
    supplement and is clearly separated so the language model never has to guess
    which facts are verified locally.
    """
    merged = dict(product or {})
    row = None
    product_id = merged.get("id")
    if product_id:
        try:
            row = _product_row(int(product_id))
        except Exception:
            row = None

    if row is not None:
        merged.update({
            "id": row.id,
            "sku": row.sku,
            "source": row.source,
            "source_id": row.source_id,
            "source_url": row.source_url,
            "name": row.name,
            "supply_price": row.supply_price,
            "sell_price": row.sell_price,
            "category": row.category,
            "brand": row.brand,
            "origin": row.origin,
            "material": row.material,
            "images": _json_list(row.images)[:_MAX_IMAGES],
            "detail_images": _json_list(row.detail_images)[:_MAX_IMAGES],
            "options": _json_list(row.options)[:_MAX_OPTIONS],
            "detail_html": row.detail_html,
            "status": row.status,
        })

    detail_text = _clean_text(merged.pop("detail_html", ""), _MAX_DETAIL_TEXT)
    source_url = str(merged.get("source_url") or "").strip()

    remote_text = ""
    remote_status = "not_attempted"
    # Stored detail text is normally richer and more reliable. Remote retrieval is
    # used only when the local detail is thin, avoiding needless supplier traffic.
    if len(detail_text) < 900 and source_url:
        remote_text, remote_status = _fetch_public_page_text(source_url)

    images = _json_list(merged.get("images"))[:_MAX_IMAGES]
    detail_images = _json_list(merged.get("detail_images"))[:_MAX_IMAGES]
    options = _json_list(merged.get("options"))[:_MAX_OPTIONS]

    verified = {
        "id": merged.get("id"),
        "sku": merged.get("sku", ""),
        "source": merged.get("source", ""),
        "source_id": merged.get("source_id", ""),
        "source_url": source_url,
        "name": merged.get("name", ""),
        "category": merged.get("category", ""),
        "brand": merged.get("brand", ""),
        "origin": merged.get("origin", ""),
        "material": merged.get("material", ""),
        "supply_price": merged.get("supply_price"),
        "sell_price": merged.get("sell_price"),
        "status": merged.get("status", ""),
        "options": options,
        "images": images,
        "detail_images": detail_images,
        "stored_detail_text": detail_text,
    }

    return {
        "verified": verified,
        "supplemental_source_page_text": remote_text,
        "source_page_fetch_status": remote_status,
        "evidence_stats": {
            "option_count": len(options),
            "image_count": len(images),
            "detail_image_count": len(detail_images),
            "stored_detail_chars": len(detail_text),
            "remote_detail_chars": len(remote_text),
        },
    }


def primary_product_image(product: dict[str, Any]) -> str:
    evidence = build_product_evidence(product)
    verified = evidence.get("verified") or {}
    images = verified.get("images") or []
    detail_images = verified.get("detail_images") or []
    for value in [*images, *detail_images]:
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
        if isinstance(value, dict):
            for key in ("url", "src", "image_url", "imageUrl"):
                url = str(value.get(key) or "")
                if url.startswith(("http://", "https://")):
                    return url
    return ""
