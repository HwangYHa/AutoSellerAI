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


def test_resolve_origin_product_no_from_channel_product_no(monkeypatch):
    uploader = _uploader(monkeypatch)
    calls: list[tuple[str, str]] = []

    def fake_get(url, **kwargs):
        calls.append(("GET", url))
        return _Resp(404, {"code": "GW.NOT_FOUND"})

    def fake_post(url, **kwargs):
        calls.append(("POST", url))
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

    monkeypatch.setattr("app.platforms.smartstore.httpx.get", fake_get)
    monkeypatch.setattr("app.platforms.smartstore.httpx.post", fake_post)

    assert uploader.resolve_origin_product_no("9988776655") == "1234567890"
    assert ("GET", f"{API}/v2/products/origin-products/9988776655") in calls
    assert ("POST", f"{API}/v1/products/search") in calls


def test_get_current_price_recovers_channel_id_to_origin_id(monkeypatch):
    uploader = _uploader(monkeypatch)

    def fake_get(url, **kwargs):
        if url.endswith("/9988776655"):
            return _Resp(404, {"code": "GW.NOT_FOUND"})
        if url.endswith("/1234567890"):
            return _Resp(200, {
                "originProduct": {"salePrice": 15900},
                "smartstoreChannelProduct": {},
            })
        raise AssertionError(url)

    monkeypatch.setattr("app.platforms.smartstore.httpx.get", fake_get)
    monkeypatch.setattr(
        uploader,
        "resolve_origin_product_no",
        lambda product_no, max_pages=50: "1234567890",
    )

    result = uploader.get_current_price("9988776655")
    assert result == {
        "ok": True,
        "price": 15900,
        "origin_product_no": "1234567890",
    }


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
