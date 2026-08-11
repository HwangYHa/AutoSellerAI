"""도매꾹 공급처 — Private API (v4.0, aid+mode+sId) + 웹스크래핑 폴백.

[도매꾹 Private API 파라미터 정리]
  - aid   : API 키 (config.domeggook_api_key)
  - mode  : 호출 모드 (getItemList 등)
  - id    : 회원 아이디 (config.domeggook_user_id)
  - sId   : 로그인 세션 (getLoginSession API로 발급)
  - ver   : 4.0 권장
  - om    : json

[현재 상태]
  - getItemList v1.x → 폐지(410 GONE)
  - getItemList v4.0 → sId 필요 (세션 기반)
  - 세션 발급: getLoginSession API → 별도 권한 신청 필요
  - 웹 스크래핑: Cloudflare 차단으로 비가용
"""
from __future__ import annotations
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urlencode, urljoin, quote

import httpx
from bs4 import BeautifulSoup

from app.config import get_settings

logger = logging.getLogger(__name__)

BASE = "https://domeggook.com"
API_BASE = "https://domeggook.com/ssl/api/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

_session_id: str | None = None
_sid_renew_date: int = 0  # setLoginChk 갱신용


def _get_session_id() -> str | None:
    """도매꾹 로그인 세션 ID 획득 (setLogin v4.1 POST).
    sId가 있어야 v4.0+ API 사용 가능.
    """
    global _session_id, _sid_renew_date
    if _session_id:
        return _session_id

    s = get_settings()
    if not s.domeggook_api_key or not s.domeggook_user_id or not s.domeggook_password:
        return None

    try:
        r = httpx.post(
            API_BASE,
            data={
                "ver": "4.1", "mode": "setLogin",
                "aid": s.domeggook_api_key,
                "id": s.domeggook_user_id,
                "pw": s.domeggook_password,
                "om": "json",
                "loginKeep": "off",
                "device": "Third Party",
                "ip": "0:0:0:0:0:0:0:0",
            },
            headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
        data = r.json()
        inner = data.get("domeggook", data)
        sid = inner.get("sId")
        if sid and str(inner.get("result", "")).lower() in ("true", "1"):
            _session_id = sid
            _sid_renew_date = int(inner.get("sIdRenewDate", 0) or 0)
            logger.info("도매꾹 로그인 성공 (sId 획득)")
        else:
            logger.info("도매꾹 로그인 실패: %s", inner)
    except Exception as e:
        logger.debug("도매꾹 세션 획득 실패: %s", e)
    return _session_id


def refresh_session() -> bool:
    """setLoginChk v4.0 — 세션 유효성 확인 및 만료 갱신."""
    global _session_id, _sid_renew_date
    if not _session_id:
        return False
    s = get_settings()
    try:
        r = httpx.post(
            API_BASE,
            data={
                "ver": "4.0", "mode": "setLoginChk",
                "aid": s.domeggook_api_key,
                "id": s.domeggook_user_id,
                "sId": _session_id,
                "loginKeep": "off",
                "sIdRenewDate": _sid_renew_date,
                "om": "json",
            },
            headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
        data = r.json()
        inner = data.get("domeggook", data)
        result = str(inner.get("result", "")).upper()
        if result == "TRUE":
            _sid_renew_date = int(inner.get("sIdRenewDate", _sid_renew_date) or _sid_renew_date)
            new_sid = inner.get("sId")
            if new_sid:
                _session_id = new_sid
            return True
        else:
            # 세션 만료 → 재로그인
            _session_id = None
            _sid_renew_date = 0
            return False
    except Exception as e:
        logger.debug("도매꾹 세션 갱신 실패: %s", e)
        return False


@dataclass
class DomeggookProduct:
    source: str = "domeggook"
    source_id: str = ""
    source_url: str = ""
    name: str = ""
    supply_price: float = 0.0
    retail_price: float = 0.0
    category: str = ""
    brand: str = ""
    origin: str = "중국"
    material: str = ""
    images: list[str] = field(default_factory=list)
    detail_images: list[str] = field(default_factory=list)
    options: list[dict] = field(default_factory=list)
    stock: int = 999


# ── 공식 API (v4.0, aid+mode) ────────────────────────────────────────────────

def _api_get(mode: str, extra: dict | None = None, ver: str = "4.0") -> dict | None:
    """도매꾹 Private API GET 호출."""
    s = get_settings()
    if not s.domeggook_api_key:
        return None

    sid = _get_session_id()
    params: dict = {
        "ver": ver,
        "mode": mode,
        "aid": s.domeggook_api_key,
        "om": "json",
    }
    if s.domeggook_user_id:
        params["id"] = s.domeggook_user_id
    if sid:
        params["sId"] = sid
    if extra:
        params.update(extra)

    try:
        r = httpx.get(API_BASE, params=params, timeout=15, headers={"User-Agent": UA})
        data = r.json()
        errors = data.get("errors") or data.get("error")
        if errors:
            code = str(errors.get("code", "") if isinstance(errors, dict) else "")
            msg = errors.get("dmessage", "") if isinstance(errors, dict) else str(errors)
            if code == "10":
                logger.debug("도매꾹 API code=10 (sId 필요 또는 파라미터 오류): %s", msg)
            elif code == "403":
                logger.info("도매꾹 API 권한 없음 (별도 신청 필요): %s", msg)
            else:
                logger.debug("도매꾹 API 에러 code=%s: %s", code, msg)
            return None
        return data.get("domeggook", data)
    except Exception as e:
        logger.debug("도매꾹 API 호출 예외: %s", e)
        return None


def _api_post(mode: str, extra: dict | None = None, ver: str = "1.0") -> dict | None:
    """도매꾹 Private API POST 호출."""
    s = get_settings()
    if not s.domeggook_api_key:
        return None

    sid = _get_session_id()
    payload: dict = {
        "ver": ver,
        "mode": mode,
        "aid": s.domeggook_api_key,
        "om": "json",
    }
    if s.domeggook_user_id:
        payload["id"] = s.domeggook_user_id
    if sid:
        payload["sId"] = sid
    if extra:
        payload.update(extra)

    try:
        r = httpx.post(
            API_BASE,
            data=payload,
            headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
        # 일부 응답은 XML
        ct = r.headers.get("content-type", "")
        if "json" in ct:
            data = r.json()
        else:
            # XML: <result>true</result> 파싱
            import xml.etree.ElementTree as ET
            try:
                root = ET.fromstring(r.text)
                data = {child.tag: child.text for child in root}
            except Exception:
                logger.debug("도매꾹 POST 응답 파싱 실패: %s", r.text[:200])
                return None
        errors = data.get("errors") or data.get("error")
        if errors:
            code = str(errors.get("code", "") if isinstance(errors, dict) else "")
            msg = errors.get("dmessage", "") if isinstance(errors, dict) else str(errors)
            logger.debug("도매꾹 POST API 에러 code=%s: %s", code, msg)
            return None
        return data.get("domeggook", data)
    except Exception as e:
        logger.debug("도매꾹 POST API 호출 예외: %s", e)
        return None


def _parse_price(val) -> float:
    if not val:
        return 0.0
    return float(re.sub(r"[^\d.]", "", str(val)) or 0)


def _abs_url(url: str) -> str:
    if not url:
        return ""
    url = url.strip()
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("http"):
        return url
    return urljoin(BASE, url)


# ── 검색 ─────────────────────────────────────────────────────────────────────

def search(keyword: str = "", page: int = 1, limit: int = 20) -> list[DomeggookProduct]:
    result = _search_api(keyword, page, limit)
    if result:
        return result
    return _search_scrape(keyword, page, limit)


def _search_api(keyword: str, page: int, limit: int) -> list[DomeggookProduct]:
    """도매꾹 상품 검색 API (v4.0).
    sId(로그인 세션) 없으면 code=10으로 실패 → 웹스크래핑 폴백.
    """
    data = _api_get("getItemList", {"keyword": keyword, "pg": page, "ic": limit})
    if not data:
        return []

    raw_list = data.get("items", [])
    if isinstance(raw_list, dict):
        raw_list = raw_list.get("item", [])
    if isinstance(raw_list, dict):
        raw_list = [raw_list]

    products = []
    for item in raw_list:
        item_no = str(item.get("itemNo", "") or item.get("no", "") or item.get("aid", ""))
        name = str(item.get("itemTitle", "") or item.get("subject", "") or item.get("title", "")).strip()
        price = _parse_price(item.get("orderAmt") or item.get("price1") or item.get("price"))
        img = _abs_url(str(item.get("itemImage150", "") or item.get("img150", "") or item.get("img1", "")))

        if not item_no or not name:
            continue
        products.append(DomeggookProduct(
            source_id=item_no,
            source_url=f"{BASE}/main/item/item_view.html?item_no={item_no}",
            name=name,
            supply_price=price,
            retail_price=_parse_price(item.get("price2") or price),
            category=str(item.get("cate_name", "") or item.get("category", "")),
            brand=str(item.get("brand", "")),
            images=[img] if img else [],
        ))
    return products


def _search_scrape(keyword: str, page: int, limit: int) -> list[DomeggookProduct]:
    url = f"{BASE}/main/item_list.html?" + urlencode({
        "m": "list", "vtype": "L", "page": page, "keyword": keyword
    })
    try:
        with httpx.Client(
            headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": BASE,
            },
            follow_redirects=True, timeout=20,
        ) as c:
            c.get(BASE)  # 홈 방문으로 쿠키 획득
            r = c.get(url)
    except Exception as e:
        logger.info("도매꾹 스크래핑 불가 (API 키 등록 필요): %s", type(e).__name__)
        return []

    # 차단 감지
    if "error_403" in str(r.url) or "error_404" in str(r.url) or r.status_code >= 400:
        logger.info("도매꾹 접근 차단 — API 키 파트너 등록 필요 (domeggook.com/main/api/overview.phtml)")
        return []

    soup = BeautifulSoup(r.text, "lxml")
    products = []

    selectors = [
        "ul.item_list > li",
        ".goods_list li",
        ".item-box",
        "li:has(.item_name)",
        "li:has(.price)",
    ]
    items = []
    for sel in selectors:
        items = soup.select(sel)
        if items:
            break

    for item in items[:limit]:
        link = item.select_one("a[href*='item_no'], a[href*='item_view'], a")
        if not link:
            continue
        href = link.get("href", "")
        m = re.search(r"item_no=([^&\s]+)|/(\d{5,})", href)
        if not m:
            continue
        item_id = m.group(1) or m.group(2)

        name = ""
        for sel in [".item_name", ".name", "strong", "h3", "h4"]:
            el = item.select_one(sel)
            if el and el.get_text(strip=True):
                name = el.get_text(strip=True)
                break
        if not name:
            name = link.get_text(strip=True)[:100]

        price = 0.0
        for sel in [".sell_price", ".price", "em", "b"]:
            el = item.select_one(sel)
            if el:
                t = re.sub(r"[^\d]", "", el.get_text())
                if t and len(t) >= 3:
                    try:
                        price = float(t)
                        break
                    except ValueError:
                        pass

        img_el = item.select_one("img")
        img_url = ""
        if img_el:
            src = img_el.get("src") or img_el.get("data-src") or ""
            img_url = _abs_url(src)

        if not name or price <= 0:
            continue
        products.append(DomeggookProduct(
            source_id=item_id,
            source_url=f"{BASE}/main/item/item_view.html?item_no={item_id}",
            name=name,
            supply_price=price,
            retail_price=price,
            images=[img_url] if img_url else [],
        ))
    return products


# ── 상품 상세 ─────────────────────────────────────────────────────────────────

def get_product(item_id: str) -> DomeggookProduct | None:
    prod = _get_product_api(item_id)
    if prod:
        return prod
    return _get_product_scrape(item_id)


def _get_product_api(item_id: str) -> DomeggookProduct | None:
    data = _api_get("getItemView", {"no": item_id})
    if not data:
        return None

    item = data.get("items", data)
    if isinstance(item, list) and item:
        item = item[0]
    elif isinstance(item, dict) and "item" in item:
        item = item["item"]
    if not isinstance(item, dict):
        return None

    name = str(item.get("itemTitle", "") or item.get("subject", "") or item.get("title", "")).strip()
    if not name:
        return None

    supply_price = _parse_price(item.get("price1") or item.get("price"))

    images = []
    for img_key in ["itemImage150", "img150", "img1", "img2", "img3", "img4", "img5", "image"]:
        v = _abs_url(str(item.get(img_key, "")))
        if v and v not in images:
            images.append(v)

    detail_images = []
    detail_raw = str(item.get("detail_img", "") or item.get("detail_html", ""))
    if detail_raw and "<img" in detail_raw:
        detail_soup = BeautifulSoup(detail_raw, "lxml")
        for img in detail_soup.select("img"):
            src = _abs_url(img.get("src", ""))
            if src and src not in images and src not in detail_images:
                detail_images.append(src)

    # 옵션
    options = []
    opts_raw = item.get("options", item.get("option"))
    if isinstance(opts_raw, dict):
        opts_raw = [opts_raw]
    if isinstance(opts_raw, list):
        for opt in opts_raw:
            if not isinstance(opt, dict):
                continue
            vals_raw = opt.get("values", opt.get("value", []))
            if isinstance(vals_raw, dict):
                vals_raw = [vals_raw.get("value", "")]
            elif isinstance(vals_raw, str):
                vals_raw = [v.strip() for v in vals_raw.split(",") if v.strip()]
            values = [str(v) for v in vals_raw if v]
            if values:
                options.append({"name": opt.get("name", "옵션"), "values": values})

    return DomeggookProduct(
        source_id=item_id,
        source_url=f"{BASE}/main/item/item_view.html?item_no={item_id}",
        name=name,
        supply_price=supply_price,
        retail_price=_parse_price(item.get("price2") or supply_price),
        category=str(item.get("cate_name", "") or item.get("category", "")),
        brand=str(item.get("brand", "")),
        origin=str(item.get("origin", "중국")),
        material=str(item.get("material", "")),
        images=images[:5],
        detail_images=detail_images[:20],
        options=options,
        stock=int(item.get("stock", 999) or 999),
    )


def _get_product_scrape(item_id: str) -> DomeggookProduct | None:
    url = f"{BASE}/main/item/item_view.html?item_no={item_id}"
    try:
        with httpx.Client(
            headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko",
                     "Referer": BASE},
            follow_redirects=True, timeout=20,
        ) as c:
            c.get(BASE)
            r = c.get(url)
    except Exception as e:
        logger.info("도매꾹 상세 접근 불가 [%s]: %s", item_id, type(e).__name__)
        return None

    if "error_403" in str(r.url) or "error_404" in str(r.url):
        logger.info("도매꾹 상세 차단 [%s]", item_id)
        return None

    soup = BeautifulSoup(r.text, "lxml")

    name = ""
    for sel in ["h1.item_name", ".item_name", "h1", "h2", "#item_name"]:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            name = el.get_text(strip=True)
            break
    if not name:
        return None

    supply_price = 0.0
    for sel in [".sell_price", "#sell_price", ".price", ".cost"]:
        el = soup.select_one(sel)
        if el:
            t = re.sub(r"[^\d]", "", el.get_text())
            if t:
                supply_price = float(t)
                break

    images: list[str] = []
    for sel in [".item_img img", "#big_img img", ".gallery img", ".main_img img"]:
        for img in soup.select(sel):
            src = _abs_url(img.get("src", "") or img.get("data-src", ""))
            if src and src not in images:
                images.append(src)

    detail_images: list[str] = []
    for sel in [".item_detail img", ".detail_content img", "#detail img"]:
        for img in soup.select(sel):
            src = _abs_url(img.get("src", "") or img.get("data-src", ""))
            if src and src not in images and src not in detail_images:
                detail_images.append(src)

    origin, material, brand, category = "중국", "", "", ""
    for row in soup.select("table tr, .spec li"):
        cells = row.select("th, td")
        if len(cells) >= 2:
            key = cells[0].get_text(strip=True)
            val = cells[1].get_text(strip=True)
            if "원산지" in key:
                origin = val
            elif "소재" in key:
                material = val
            elif "브랜드" in key or "제조사" in key:
                brand = val
            elif "카테고리" in key or "분류" in key:
                category = val

    return DomeggookProduct(
        source_id=item_id,
        source_url=url,
        name=name,
        supply_price=supply_price,
        images=images[:5],
        detail_images=detail_images[:20],
        category=category,
        origin=origin,
        material=material,
        brand=brand,
    )


# ── 주문 관리 ─────────────────────────────────────────────────────────────────

@dataclass
class OrderListHeader:
    total: int = 0
    current_page: int = 1
    first_item: int = 1
    last_item: int = 0
    per_page: int = 20
    total_pages: int = 1


@dataclass
class OrderSummary:
    order_no: str = ""
    order_uid: str = ""
    status: str = ""
    item_no: str = ""
    item_title: str = ""
    market: str = ""
    image_url: str = ""
    qty: int = 0
    amount: int = 0
    amount_pay: int = 0
    date: str = ""


@dataclass
class OrderDetail:
    order_no: str = ""
    order_uid: str = ""
    status: str = ""
    status_mode: str = ""
    order_memo: str = ""
    qty: int = 0
    amount_pay: int = 0
    amount: int = 0
    supply_amount: int = 0
    date: str = ""
    item: dict = field(default_factory=dict)
    pay: dict = field(default_factory=dict)
    seller_info: dict = field(default_factory=dict)
    buyer_info: dict = field(default_factory=dict)
    consumer: dict = field(default_factory=dict)
    delivery: dict = field(default_factory=dict)
    select_opt: list = field(default_factory=list)
    is_back: bool = False
    deny_date: int = 0
    deny_memo: str = ""
    serv: dict = field(default_factory=dict)
    log: str = ""


def _parse_order_summary(raw: dict) -> OrderSummary:
    return OrderSummary(
        order_no=str(raw.get("orderNo", "")),
        order_uid=str(raw.get("orderUid", "")),
        status=str(raw.get("status", "")),
        item_no=str(raw.get("itemNo", "")),
        item_title=str(raw.get("itemTitle", "")),
        market=str(raw.get("market", "")),
        image_url=_abs_url(str(raw.get("itemImage150", "") or raw.get("itemImage075", ""))),
        qty=int(raw.get("orderQty", 0) or 0),
        amount=int(raw.get("orderAmt", 0) or 0),
        amount_pay=int(raw.get("orderAmtPay", 0) or 0),
        date=str(raw.get("date", "")),
    )


def _parse_order_detail(raw: dict) -> OrderDetail:
    opts_raw = raw.get("selectOpt", {}) or {}
    opt_list = opts_raw.get("opt", []) if isinstance(opts_raw, dict) else []
    if isinstance(opt_list, dict):
        opt_list = [opt_list]

    return OrderDetail(
        order_no=str(raw.get("orderNo", "")),
        order_uid=str(raw.get("orderUid", "")),
        status=str(raw.get("status", "")),
        status_mode=str(raw.get("statusMode", "")),
        order_memo=str(raw.get("orderMemo", "")),
        qty=int(raw.get("orderQty", 0) or 0),
        amount_pay=int(raw.get("orderAmtPay", 0) or 0),
        amount=int(raw.get("orderAmount", 0) or 0),
        supply_amount=int(raw.get("supplyAmount", 0) or 0),
        date=str(raw.get("date", "")),
        item=raw.get("item", {}),
        pay=raw.get("pay", {}),
        seller_info=raw.get("sellerInfo", {}),
        buyer_info=raw.get("buyerInfo", {}),
        consumer=raw.get("consumer", {}),
        delivery=raw.get("delivery", {}),
        select_opt=opt_list,
        is_back=str(raw.get("isBack", "false")).lower() == "true",
        deny_date=int(raw.get("denyDate", 0) or 0),
        deny_memo=str(raw.get("denyMemo", "")),
        serv=raw.get("serv", {}),
        log=str(raw.get("log", "")),
    )


def _extract_items_list(data: dict) -> list[dict]:
    items = data.get("items", [])
    if isinstance(items, dict):
        items = list(items.values()) if items else []
    return items if isinstance(items, list) else []


# ── 구매 주문서 목록 조회 (for=buy) ──────────────────────────────────────────

def get_buy_order_list(
    *,
    days: int = 30,
    order_no: str | None = None,
    order_uid: str | None = None,
    item_no: str | None = None,
    status: str | None = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[OrderListHeader, list[OrderSummary]]:
    extra: dict = {"for": "buy", "pg": page, "ic": per_page, "day": days}
    if order_no:
        extra["no"] = order_no
    if order_uid:
        extra["uid"] = order_uid
    if item_no:
        extra["itemNo"] = item_no
    if status:
        extra["st"] = status

    data = _api_get("getOrderList", extra)
    if not data:
        return OrderListHeader(), []

    hdr_raw = data.get("header", {}) or {}
    header = OrderListHeader(
        total=int(hdr_raw.get("numberOfItems", 0) or 0),
        current_page=int(hdr_raw.get("currentPage", 1) or 1),
        first_item=int(hdr_raw.get("firstItem", 1) or 1),
        last_item=int(hdr_raw.get("lastItem", 0) or 0),
        per_page=int(hdr_raw.get("itemsPerPage", per_page) or per_page),
        total_pages=int(hdr_raw.get("numberOfPages", 1) or 1),
    )
    orders = [_parse_order_summary(r) for r in _extract_items_list(data)]
    return header, orders


# ── 구매 주문서 상세 조회 (for=buy) ──────────────────────────────────────────

def get_buy_order_detail(order_no: str | None = None, order_uid: str | None = None) -> OrderDetail | None:
    if not order_no and not order_uid:
        return None
    extra: dict = {"for": "buy"}
    if order_no:
        extra["no"] = order_no
    if order_uid:
        extra["uid"] = order_uid

    data = _api_get("getOrderView", extra)
    if not data:
        return None
    items = _extract_items_list(data)
    return _parse_order_detail(items[0]) if items else None


# ── 구매취소 신청 ─────────────────────────────────────────────────────────────

def cancel_buy_order(order_no: str, memo: str) -> str | None:
    """구매취소 신청. 반환값: 'true' | 'complete' | 'req' | None(실패)"""
    data = _api_post("setOrdDeny", {"type": "buy", "no": order_no, "memo": memo})
    if not data:
        return None
    return str(data.get("result", ""))


# ── 판매 주문서 목록 조회 (for=sell) ─────────────────────────────────────────

def get_sell_order_list(
    *,
    days: int = 30,
    order_no: str | None = None,
    order_uid: str | None = None,
    item_no: str | None = None,
    status: str | None = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[OrderListHeader, list[OrderSummary]]:
    extra: dict = {"for": "sell", "pg": page, "ic": per_page, "day": days}
    if order_no:
        extra["no"] = order_no
    if order_uid:
        extra["uid"] = order_uid
    if item_no:
        extra["itemNo"] = item_no
    if status:
        extra["st"] = status

    data = _api_get("getOrderList", extra)
    if not data:
        return OrderListHeader(), []

    hdr_raw = data.get("header", {}) or {}
    header = OrderListHeader(
        total=int(hdr_raw.get("numberOfItems", 0) or 0),
        current_page=int(hdr_raw.get("currentPage", 1) or 1),
        first_item=int(hdr_raw.get("firstItem", 1) or 1),
        last_item=int(hdr_raw.get("lastItem", 0) or 0),
        per_page=int(hdr_raw.get("itemsPerPage", per_page) or per_page),
        total_pages=int(hdr_raw.get("numberOfPages", 1) or 1),
    )
    orders = [_parse_order_summary(r) for r in _extract_items_list(data)]
    return header, orders


# ── 판매 주문서 상세 조회 (for=sell) ─────────────────────────────────────────

def get_sell_order_detail(order_no: str | None = None, order_uid: str | None = None) -> OrderDetail | None:
    if not order_no and not order_uid:
        return None
    extra: dict = {"for": "sell"}
    if order_no:
        extra["no"] = order_no
    if order_uid:
        extra["uid"] = order_uid

    data = _api_get("getOrderView", extra)
    if not data:
        return None
    items = _extract_items_list(data)
    return _parse_order_detail(items[0]) if items else None


# ── 판매취소 신청 ─────────────────────────────────────────────────────────────

def cancel_sell_order(order_no: str, memo: str) -> str | None:
    """판매취소 신청. 반환값: 'true' | None(실패)"""
    data = _api_post("setOrdDeny", {"type": "sell", "no": order_no, "memo": memo})
    if not data:
        return None
    return str(data.get("result", ""))


# ── 주문서 발주확인 (공급사용) ────────────────────────────────────────────────

def confirm_order(order_nos: list[str]) -> dict:
    """발주확인 처리. 반환: {"result": bool, "success": [...], "fail": [...]}"""
    if not order_nos:
        return {"result": False, "success": [], "fail": []}
    data = _api_post("setOrdChk", {"no": ",".join(order_nos)})
    if not data:
        return {"result": False, "success": [], "fail": order_nos}

    def _to_list(val) -> list[str]:
        if not val:
            return []
        if isinstance(val, dict):
            nos = val.get("no", [])
            return [str(nos)] if isinstance(nos, (str, int)) else [str(n) for n in nos]
        return []

    return {
        "result": str(data.get("result", "false")).lower() == "true",
        "success": _to_list(data.get("success")),
        "fail": _to_list(data.get("fail")),
    }


# ── 발송정보 입력/수정 (공급사용) ─────────────────────────────────────────────

DELI_COMPANY_CODES = {
    "CJ대한통운": "DAEHAN", "건영택배": "KUNYOUNG", "로젠택배": "KGBL",
    "우체국택배": "EPOST", "일양택배": "ILYANG", "한진택배": "HANJIN",
    "롯데택배": "HYUNDAI", "GS편의점택배": "CVSNET", "천일택배": "CHUNIL",
    "대신택배": "DAESIN", "경동택배": "KYUNGDONG", "우리택배": "HANSEO",
    "합동택배": "HDEXP", "한의사랑택배": "HPL", "CU편의점택배": "CU",
    "홈픽택배": "HOMEPICK", "용마로지스": "YONGMA", "컬리넥스트마일": "NEXTMILE",
}


def register_delivery(
    order_no: str,
    deli_company: str,
    deli_code: str,
    *,
    deli_method: str = "TB",
    deli_with_tax: int = 0,
    is_edit: bool = False,
) -> bool:
    """발송정보 등록(add) 또는 수정(edit)."""
    data = _api_post("setOrdOkDeli", {
        "no": order_no,
        "type": "edit" if is_edit else "add",
        "deliMethod": deli_method,
        "deliCompany": deli_company,
        "deliCode": deli_code,
        "deliWithTax": deli_with_tax,
    })
    if not data:
        return False
    return str(data.get("result", "false")).lower() == "true"


# ── 전체 품절 확인 목록 ───────────────────────────────────────────────────────

@dataclass
class SupplyStatus:
    item_no: str = ""
    title: str = ""
    status: str = ""
    image_url: str = ""
    category: str = ""
    seller: str = ""
    price: int = 0
    qty: int = 0
    supply_qty: int = 0
    date: int = 0


def get_supply_status_list(
    *,
    status: str | None = None,
    category: str | None = None,
    date: str | None = None,
    search_type: str | None = None,
    search_word: str | None = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[OrderListHeader, list[SupplyStatus]]:
    """전체 품절/상태 변경 목록 조회 (ver 1.0)."""
    extra: dict = {"type": "all", "pg": page, "ic": per_page}
    if status:
        extra["status"] = status
    if category:
        extra["cate"] = category
    if date:
        extra["date"] = date
    if search_type:
        extra["sc"] = search_type
    if search_word:
        extra["sw"] = search_word

    data = _api_get("getAllSupplyChk", extra, ver="1.0")
    if not data:
        return OrderListHeader(), []

    hdr_raw = data.get("header", {}) or {}
    header = OrderListHeader(
        total=int(hdr_raw.get("numberOfItems", 0) or 0),
        current_page=int(hdr_raw.get("currentPage", 1) or 1),
        first_item=int(hdr_raw.get("firstItem", 1) or 1),
        last_item=int(hdr_raw.get("lastItem", 0) or 0),
        per_page=int(hdr_raw.get("itemsPerPage", per_page) or per_page),
        total_pages=int(hdr_raw.get("numberOfPages", 1) or 1),
    )

    raw_items = data.get("items", {}) or {}
    if isinstance(raw_items, dict):
        raw_list = raw_items.get("item", [])
        if isinstance(raw_list, dict):
            raw_list = [raw_list]
    elif isinstance(raw_items, list):
        raw_list = raw_items
    else:
        raw_list = []

    items = [
        SupplyStatus(
            item_no=str(r.get("no", "")),
            title=str(r.get("title", "")),
            status=str(r.get("status", "")),
            image_url=_abs_url(str(r.get("img", ""))),
            category=str(r.get("category", "")),
            seller=str(r.get("seller", "")),
            price=int(r.get("price", 0) or 0),
            qty=int(r.get("qty", 0) or 0),
            supply_qty=int(r.get("supplyQty", 0) or 0),
            date=int(r.get("date", 0) or 0),
        )
        for r in raw_list
    ]
    return header, items


# ── 공통 POST 헬퍼 (bracket key 지원) ────────────────────────────────────────

def _post_raw(data_pairs: list[tuple]) -> dict | None:
    """httpx POST with tuple-list payload (bracket-style keys 지원)."""
    import xml.etree.ElementTree as ET
    s = get_settings()
    sid = _get_session_id()
    base_pairs: list[tuple] = [
        ("aid", s.domeggook_api_key),
        ("id", s.domeggook_user_id),
        ("om", "json"),
    ]
    if sid:
        base_pairs.append(("sId", sid))
    payload = base_pairs + list(data_pairs)
    try:
        r = httpx.post(
            API_BASE,
            data=payload,
            headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
        ct = r.headers.get("content-type", "")
        if "json" in ct:
            data = r.json()
            return data.get("domeggook", data)
        try:
            root = ET.fromstring(r.text)
            return {child.tag: child.text for child in root}
        except Exception:
            logger.debug("도매꾹 응답 파싱 실패: %s", r.text[:200])
            return None
    except Exception as e:
        logger.debug("도매꾹 POST 예외: %s", e)
        return None


# ── 상품 번호 전송 (Stomp API) ────────────────────────────────────────────────

def enqueue_item_nos(item_nos: list[str]) -> dict:
    """setItemNoEnqueue — 상품번호를 Stomp API에 enqueue.
    반환: {"res": bool, "cnt": int, "no_enqueue": [...]}
    """
    import json as _json
    data = _post_raw([
        ("ver", "1.0"),
        ("mode", "setItemNoEnqueue"),
        ("itemNo", _json.dumps(item_nos)),
    ])
    if not data:
        return {"res": False, "cnt": 0, "no_enqueue": []}
    no_enq_raw = (data.get("data") or {}).get("noEnqueue", []) if isinstance(data.get("data"), dict) else []
    if isinstance(no_enq_raw, str):
        no_enq_raw = [no_enq_raw]
    return {
        "res": str(data.get("res", "false")).lower() == "true",
        "cnt": int(data.get("cnt", 0) or 0),
        "no_enqueue": no_enq_raw,
    }


# ── 상품 진열상태 변경 ────────────────────────────────────────────────────────

def set_item_display(item_display: dict[str, bool]) -> bool:
    """setItemDisplay — 복수 상품의 진열여부 일괄 변경.
    item_display: {상품번호: True/False}
    """
    pairs: list[tuple] = [("ver", "1.0"), ("mode", "setItemDisplay")]
    for item_no, visible in item_display.items():
        pairs.append((f"disp[{item_no}]", "true" if visible else "false"))
    data = _post_raw(pairs)
    if not data:
        return False
    return str(data.get("result", "false")).lower() == "true"


# ── 상품재고 변경 (단일상품) ──────────────────────────────────────────────────

def set_item_qty(item_qty: dict[str, int]) -> bool:
    """setItemQty — 옵션 없는 상품의 재고 일괄 변경.
    item_qty: {상품번호: 재고수량}. 0 입력 시 품절처리.
    """
    pairs: list[tuple] = [("ver", "1.0"), ("mode", "setItemQty")]
    for item_no, qty in item_qty.items():
        pairs.append((f"qty[{item_no}]", str(max(0, qty))))
    data = _post_raw(pairs)
    if not data:
        return False
    return str(data.get("result", "false")).lower() == "true"


# ── 주문옵션 재고/판매상태 수정 ───────────────────────────────────────────────

def set_item_option_update(
    item_no: str,
    options: list[dict],
) -> dict:
    """setItemOptionUpdate v1.1 — 옵션 재고/노출/판매상태 수정.

    options 리스트 각 항목:
      {
        "disp_dome": 1,      # 도매꾹 노출 (0/1)
        "disp_domeme": 1,    # 도매매 노출 (0/1)
        "amt_dome": 0,       # 도매꾹 옵션추가금
        "amt_domeme": 0,     # 도매매 옵션추가금
        "qty": 99,           # 재고
        "hid": 0,            # 0:판매중 1:판매종료 2:숨김
      }
    반환: {"result": "SUCCESS"|에러코드, "item_no": str}
    """
    pairs: list[tuple] = [
        ("ver", "1.1"),
        ("mode", "setItemOptionUpdate"),
        ("itemNo", item_no),
    ]
    for opt in options:
        pairs.append(("dispDomeggook[]", str(opt.get("disp_dome", 1))))
        pairs.append(("dispDomeme[]", str(opt.get("disp_domeme", 1))))
        if "amt_dome" in opt:
            pairs.append(("amtDomeggook[]", str(opt["amt_dome"])))
        if "amt_domeme" in opt:
            pairs.append(("amtDomeme[]", str(opt["amt_domeme"])))
        pairs.append(("qty[]", str(max(0, int(opt.get("qty", 0))))))
        pairs.append(("hid[]", str(opt.get("hid", 0))))
    data = _post_raw(pairs)
    if not data:
        return {"result": "ERROR", "item_no": item_no}
    return {
        "result": str(data.get("result", "ERROR")),
        "item_no": str(data.get("no", item_no)),
    }


# ── 상품 등록/수정 ────────────────────────────────────────────────────────────

def set_item_batch(items: list[dict], *, model: str = "insert") -> list[dict]:
    """setItemBatch v4.1 — 상품 최대 10개 일괄 등록/수정.

    items: 각 상품 dict (API 문서의 item[] JSON 필드 내용).
           신규등록: itemNo 불필요. 수정: itemNo 필수.
    model: "insert" | "update"
    반환: [{"key": str, "result": "SUCCESS"|에러코드, "batch_no": str}, ...]
    """
    import json as _json
    if not items:
        return []

    pairs: list[tuple] = [
        ("ver", "4.1"),
        ("mode", "setItemBatch"),
        ("model", model),
        ("oe", "utf-8"),
        ("om", "json"),
    ]
    s = get_settings()
    sid = _get_session_id()
    pairs += [("aid", s.domeggook_api_key), ("id", s.domeggook_user_id)]
    if sid:
        pairs.append(("sId", sid))

    for idx, item_data in enumerate(items[:10]):
        key = str(item_data.get("itemCustomCode", idx) or idx)
        pairs.append((f"item[{key}]", _json.dumps(item_data, ensure_ascii=False)))

    try:
        import xml.etree.ElementTree as ET
        r = httpx.post(
            API_BASE,
            data=pairs,
            headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        ct = r.headers.get("content-type", "")
        if "json" in ct:
            raw = r.json().get("domeggook", r.json())
        else:
            root = ET.fromstring(r.text)
            raw = {child.tag: child.text for child in root}
    except Exception as e:
        logger.debug("setItemBatch 예외: %s", e)
        return [{"key": "", "result": "ERROR", "batch_no": ""}]

    # 단일 등록 vs 복수 등록 응답 통일
    if isinstance(raw, list):
        return [{"key": str(r.get("key", "")), "result": str(r.get("result", "")), "batch_no": str(r.get("no", ""))} for r in raw]
    return [{"key": str(raw.get("key", "")), "result": str(raw.get("result", "")), "batch_no": str(raw.get("no", ""))}]


# ── 상품 대량등록 상태확인 ────────────────────────────────────────────────────

def get_batch_status(batch_keys: list[str], status_filter: str | None = None) -> list[dict]:
    """getChkBatchKey v4.0 — 대량등록번호로 등록 상태 조회.
    반환: [{"batch_no": str, "status": str, "item_no": str, "error": str}, ...]
    """
    if not batch_keys:
        return []
    extra: dict = {"key": ",".join(batch_keys)}
    if status_filter:
        extra["status"] = status_filter
    data = _api_post("getChkBatchKey", extra, ver="4.0")
    if not data:
        return []
    raw_data = data.get("data", [])
    if isinstance(raw_data, dict):
        raw_data = [raw_data]
    return [
        {
            "batch_no": str(r.get("no", "")),
            "status": str(r.get("status", "")),
            "item_no": str(r.get("itemNo", "")),
            "error": str(r.get("error", "")),
        }
        for r in (raw_data or [])
    ]


# ── 출고/반품지 등록 및 수정 ──────────────────────────────────────────────────

def set_deli_place(
    title: str,
    zipcode: str,
    address1: str,
    *,
    address2: str = "",
    phone: str = "",
    mobile: str = "",
    sano: str | None = None,
) -> dict:
    """setDeliPlace — 출고/반품지 신규등록(sano=None) 또는 수정(sano=번호).
    반환: {"result": bool, "sano": str}
    """
    pairs: list[tuple] = [
        ("ver", "1.0"), ("mode", "setDeliPlace"),
        ("type", "update" if sano else "insert"),
        ("title", title), ("zipcode", zipcode), ("address1", address1),
    ]
    if address2:
        pairs.append(("address2", address2))
    if phone:
        pairs.append(("phone", phone))
    if mobile:
        pairs.append(("mobile", mobile))
    if sano:
        pairs.append(("sano", sano))
    data = _post_raw(pairs)
    if not data:
        return {"result": False, "sano": ""}
    return {
        "result": str(data.get("result", "false")).lower() == "true",
        "sano": str(data.get("sano", "")),
    }


# ── 출고/반품지 정보 조회 ─────────────────────────────────────────────────────

@dataclass
class DeliPlace:
    sano: str = ""
    title: str = ""
    zipcode: str = ""
    address1: str = ""
    address2: str = ""
    phone: str = ""
    mobile: str = ""


def get_deli_place(sano: str | None = None) -> list[DeliPlace]:
    """getDeliPlace — 출고/반품지 정보 조회.
    sano: None이면 전체 조회. 복수 조회는 ','로 연결 (SA 접두사 제외, 숫자만).
    """
    import xml.etree.ElementTree as ET
    s = get_settings()
    sid = _get_session_id()
    payload: list[tuple] = [
        ("ver", "1.0"), ("mode", "getDeliPlace"),
        ("aid", s.domeggook_api_key), ("id", s.domeggook_user_id),
    ]
    if sid:
        payload.append(("sId", sid))
    if sano:
        payload.append(("sano", sano))

    try:
        r = httpx.post(
            API_BASE,
            data=payload,
            headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
        root = ET.fromstring(r.text)
    except Exception as e:
        logger.debug("getDeliPlace 예외: %s", e)
        return []

    result = []
    for info in root.findall("info"):
        def _t(tag: str) -> str:
            el = info.find(tag)
            return el.text.strip() if el is not None and el.text else ""
        result.append(DeliPlace(
            sano=_t("sano"), title=_t("title"), zipcode=_t("zipcode"),
            address1=_t("address1"), address2=_t("address2"),
            phone=_t("phone"), mobile=_t("mobile"),
        ))
    return result


# ── 반품/교환 신청내역 조회 ───────────────────────────────────────────────────

def get_order_return(order_no: str) -> dict:
    """getOrderReturn v1.0 — 특정 주문서의 반품/교환 신청 내역.
    반환: {"order": dict, "item": dict, "return": dict}
    """
    data = _api_get("getOrderReturn", {"orderNo": order_no}, ver="1.0")
    if not data:
        return {}
    return {
        "order": data.get("order", {}),
        "item": data.get("item", {}),
        "return": data.get("return", {}),
    }


# ── 상품문의글 목록 조회 ──────────────────────────────────────────────────────

def list_item_supports(
    search_type: str,
    *,
    item_no: str | None = None,
    writer_id: str | None = None,
    seller_id: str | None = None,
    sup_no: int | None = None,
    status: str | None = None,
    title: str | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[OrderListHeader, list[dict]]:
    """listItemSup v1.0 — 상품문의글 목록 조회.
    search_type: "item" | "writer" | "seller"
    """
    extra: dict = {"type": search_type, "pg": page, "ic": per_page}
    if item_no:
        extra["itemNo"] = item_no
    if writer_id:
        extra["writeId"] = writer_id
    if seller_id:
        extra["sellId"] = seller_id
    if sup_no is not None:
        extra["supNo"] = sup_no
    if status:
        extra["status"] = status
    if title:
        extra["title"] = title
    if date_start:
        extra["dateStart"] = date_start
    if date_end:
        extra["dateEnd"] = date_end

    data = _api_post("listItemSup", extra, ver="1.0")
    if not data:
        return OrderListHeader(), []

    hdr_raw = data.get("header", {}) or {}
    header = OrderListHeader(
        total=int(hdr_raw.get("numberOfItems", 0) or 0),
        current_page=int(hdr_raw.get("currentPage", 1) or 1),
        first_item=int(hdr_raw.get("firstItem", 1) or 1),
        last_item=int(hdr_raw.get("lastItem", 0) or 0),
        per_page=int(hdr_raw.get("itemsPerPage", per_page) or per_page),
        total_pages=int(hdr_raw.get("numberOfPages", 1) or 1),
    )
    supports_raw = data.get("supports", {}) or {}
    support_list = supports_raw.get("support", []) if isinstance(supports_raw, dict) else supports_raw
    if isinstance(support_list, dict):
        support_list = [support_list]
    return header, support_list


# ── 상품문의글 상세조회 ───────────────────────────────────────────────────────

def show_item_support(sup_no: int) -> dict:
    """showItemSup v1.0 — 특정 상품문의글 상세 조회.
    반환: {"item": dict, "receive": dict, "contents": dict, "comments": list}
    """
    data = _api_post("showItemSup", {"supNo": sup_no}, ver="1.0")
    if not data:
        return {}
    comments_raw = data.get("comments", {}) or {}
    comment_list = comments_raw.get("comment", []) if isinstance(comments_raw, dict) else comments_raw
    if isinstance(comment_list, dict):
        comment_list = [comment_list]
    return {
        "item": data.get("item", {}),
        "receive": data.get("receive", {}),
        "contents": data.get("contents", {}),
        "comments": comment_list,
    }


# ── 상품문의글 답글 등록 ──────────────────────────────────────────────────────

def write_item_support_comment(sup_no: int, memo: str, *, secret: int = 0) -> dict:
    """writeItemSupCom v1.0 — 상품문의글에 답변 등록.
    반환: {"result": bool, "sup_no": int, "sup_com_no": int}
    """
    data = _api_post("writeItemSupCom", {"supNo": sup_no, "memo": memo, "secret": secret}, ver="1.0")
    if not data:
        return {"result": False, "sup_no": sup_no, "sup_com_no": 0}
    return {
        "result": str(data.get("result", "false")).lower() == "true",
        "sup_no": int(data.get("supNo", sup_no) or sup_no),
        "sup_com_no": int(data.get("supComNo", 0) or 0),
    }


# ── 상품 상세정보 조회 (ES 기반, 고속) ───────────────────────────────────────

def get_item_view_es(
    item_nos: list[str],
    *,
    market: str | None = None,
    all_item: bool = False,
    seller_id: str | None = None,
) -> list[dict]:
    """getItemViewES v4.0 — ES 기반 상품 상세 조회 (최대 100개).
    반환: 각 상품 dict 리스트 (basis, price, qty, deli, thumb, desc, selectOpt, seller 포함)
    """
    if not item_nos:
        return []
    s = get_settings()
    extra: dict = {"no": ",".join(item_nos[:100])}
    if market:
        extra["market"] = market
    if all_item and seller_id:
        extra["allItem"] = "true"
        extra["sellerId"] = seller_id
        sid = _get_session_id()
        if sid:
            extra["sId"] = sid

    params: dict = {
        "ver": "4.0",
        "mode": "getItemViewES",
        "aid": s.domeggook_api_key,
        "om": "json",
    }
    params.update(extra)

    try:
        r = httpx.get(API_BASE, params=params, timeout=15, headers={"User-Agent": UA})
        data = r.json()
        inner = data.get("domeggook", data)
        items = inner.get("items", inner)
        if isinstance(items, dict):
            items = list(items.values())
        return items if isinstance(items, list) else []
    except Exception as e:
        logger.debug("getItemViewES 예외: %s", e)
        return []


# ── 주문서 생성 ───────────────────────────────────────────────────────────────

@dataclass
class OrderItem:
    """setOrder API의 item[] 파라미터 구조 (v4.3).

    item[상품번호] 값 형식:
      market||payment_method||option_code|quantity||seller_memo||delivery_req

    - market: "dome" (도매꾹) | "supply" (도매매)
    - payment_method: "P" (선결제) | "B" (착불) | "F" (무료)
    - option_code: 주문옵션코드 (없으면 빈 문자열)
    - quantity: 주문 수량
    - seller_memo: 판매자 전달사항 (선택)
    - delivery_req: 배송 요청사항 (선택)
    """
    item_no: str
    quantity: int = 1
    market: str = "dome"
    payment_method: str = "P"
    option_code: str = ""
    seller_memo: str = ""
    delivery_req: str = ""

    def to_param_value(self) -> str:
        return f"{self.market}||{self.payment_method}||{self.option_code}|{self.quantity}||{self.seller_memo}||{self.delivery_req}"


@dataclass
class DeliInfo:
    """setOrder API의 deliinfo 파라미터 구조.

    deliinfo 값 형식:
      name|email|zipcode|address1|address2|phone|tel|company
    """
    name: str
    zipcode: str
    address1: str
    address2: str = ""
    email: str = ""
    phone: str = ""
    tel: str = ""
    company: str = ""

    def to_param_value(self) -> str:
        return f"{self.name}|{self.email}|{self.zipcode}|{self.address1}|{self.address2}|{self.phone}|{self.tel}|{self.company}"


def create_order(
    items: list[OrderItem],
    deli_info: DeliInfo,
    *,
    receipt: int = 0,
    alliance: str = "",
    encoding: str = "utf-8",
) -> list[dict]:
    """setOrder v4.3 — e-money로 주문서 생성.

    반환: [{"order_no": str, "item_no": str, "recipient": str}, ...]
          실패 시 빈 리스트.

    주의: 실제 결제가 발생합니다. e-money 잔액 확인 후 호출하세요.
    """
    if not items:
        return []

    s = get_settings()
    sid = _get_session_id()
    if not sid:
        logger.warning("도매꾹 주문서 생성 실패: 로그인 세션 없음")
        return []

    import xml.etree.ElementTree as ET

    payload: list[tuple] = [
        ("ver", "4.3"),
        ("mode", "setOrder"),
        ("aid", s.domeggook_api_key),
        ("id", s.domeggook_user_id),
        ("sId", sid),
        ("receipt", str(receipt)),
        ("deliinfo", deli_info.to_param_value()),
        ("ie", encoding),
        ("oe", encoding),
        ("om", "json"),
    ]
    if alliance:
        payload.append(("alliance", alliance))
    for order_item in items:
        payload.append((f"item[{order_item.item_no}]", order_item.to_param_value()))

    try:
        r = httpx.post(
            API_BASE,
            data=payload,
            headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        ct = r.headers.get("content-type", "")
        if "json" in ct:
            data = r.json().get("domeggook", r.json())
        else:
            root = ET.fromstring(r.text)
            data = {child.tag: child.text for child in root}
    except Exception as e:
        logger.error("도매꾹 주문서 생성 예외: %s", e)
        return []

    result_val = str(data.get("result", "")).upper()
    if result_val != "SUCCESS":
        logger.warning("도매꾹 주문서 생성 실패: result=%s", result_val)
        return []

    raw_orders = data.get("order", [])
    if isinstance(raw_orders, dict):
        raw_orders = [raw_orders]
    return [
        {
            "order_no": str(o.get("orderNo", "")),
            "item_no": str(o.get("itemNo", "")),
            "recipient": str(o.get("getName", "")),
        }
        for o in (raw_orders or [])
    ]
