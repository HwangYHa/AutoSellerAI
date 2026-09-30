from __future__ import annotations

from app.platforms.smartstore import API, SmartStoreUploader


class _Resp:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or str(self._payload)

    def json(self):
        return self._payload


def _uploader(monkeypatch) -> SmartStoreUploader:
    uploader = object.__new__(SmartStoreUploader)
    monkeypatch.setattr(uploader, "_ensure_token", lambda: None)
    monkeypatch.setattr(uploader, "_headers", lambda: {"Authorization": "Bearer test"})
    return uploader


def test_resolve_origin_product_no_from_channel_product_no_uses_exact_search(monkeypatch):
    uploader = _uploader(monkeypatch)
    bodies: list[dict] = []

    def fake_post(url, **kwargs):
        assert url == f"{API}/v1/products/search"
        bodies.append(kwargs["json"])
        body = kwargs["json"]
        if body["searchKeywordType"] == "PRODUCT_NO":
            return _Resp(200, {"contents": [], "last": True})
        return _Resp(200, {
            "contents": [{
                "originProductNo": 1234567890,
                "channelProducts": [{
                    "channelServiceType": "STOREFARM",
                    "channelProductNo": 9988776655,
                    "salePrice": 15900,
                }],
            }],
            "last": True,
        })

    monkeypatch.setattr("app.platforms.smartstore.httpx.post", fake_post)

    assert uploader.resolve_origin_product_no("9988776655") == "1234567890"
    assert bodies[0]["searchKeywordType"] == "PRODUCT_NO"
    assert bodies[0]["originProductNos"] == [9988776655]
    assert bodies[1]["searchKeywordType"] == "CHANNEL_PRODUCT_NO"
    assert bodies[1]["channelProductNos"] == [9988776655]


def test_get_current_price_recovers_channel_id_to_origin_id(monkeypatch):
    uploader = _uploader(monkeypatch)

    def fake_get(url, **kwargs):
        if url.endswith("/9988776655"):
            return _Resp(404, {"code": "NOT_FOUND"})
        if url.endswith("/1234567890"):
            return _Resp(200, {
                "originProduct": {"salePrice": 15900},
                "smartstoreChannelProduct": {},
            })
        raise AssertionError(url)

    monkeypatch.setattr("app.platforms.smartstore.httpx.get", fake_get)
    monkeypatch.setattr(
        uploader,
        "_search_product_identity",
        lambda product_no: {
            "found": True,
            "origin_product_no": "1234567890",
            "channel_product_no": "9988776655",
            "status": "SALE",
        },
    )

    result = uploader.get_current_price("9988776655")
    assert result == {
        "ok": True,
        "price": 15900,
        "origin_product_no": "1234567890",
    }


def test_get_current_price_classifies_truly_missing_product(monkeypatch):
    uploader = _uploader(monkeypatch)
    monkeypatch.setattr(
        "app.platforms.smartstore.httpx.get",
        lambda *args, **kwargs: _Resp(404, {"code": "NOT_FOUND", "message": "존재하지 않는 상품입니다."}),
    )
    monkeypatch.setattr(
        uploader,
        "_search_product_identity",
        lambda product_no: {
            "found": False,
            "origin_product_no": "",
            "channel_product_no": "",
            "status": "",
        },
    )

    result = uploader.get_current_price("9988776655")
    assert result["ok"] is False
    assert result["not_found"] is True
    assert "현재 상품목록에 존재하지 않는 상품" in result["error"]


def test_update_price_uses_current_origin_product_endpoint_after_recovery(monkeypatch):
    uploader = _uploader(monkeypatch)
    put_calls: list[tuple[str, dict]] = []

    monkeypatch.setattr(
        uploader,
        "_get_origin_product",
        lambda product_no: (
            "1234567890",
            {"originProduct": {"salePrice": 15900}, "smartstoreChannelProduct": {}},
            "",
        ),
    )

    def fake_put(url, **kwargs):
        put_calls.append((url, kwargs["json"]))
        return _Resp(200, {"ok": True})

    monkeypatch.setattr("app.platforms.smartstore.httpx.put", fake_put)

    result = uploader.update_price("9988776655", 17900)
    assert result["ok"] is True
    assert result["origin_product_no"] == "1234567890"
    assert put_calls[0][0] == f"{API}/v2/products/origin-products/1234567890"
    assert put_calls[0][1]["originProduct"]["salePrice"] == 17900
