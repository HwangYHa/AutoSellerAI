from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from app.os.bulk_market_tools import apply_bulk_product_xlsx, stage_marketplace_clone
from app.os.channel_template_runtime import install_channel_template_runtime
from app.os.commerce_automation import (
    generate_ai_inquiry_draft,
    run_inventory_automation,
    save_scheduler_rule,
    sync_claims,
    sync_inquiries,
    sync_settlements,
)
from app.os.payment_orchestrator import prepare_payment, sync_payment_sessions
from app.platforms import commerce_ops_api


class FakeResponse:
    def __init__(self, payload, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = ""
        self.content = b"{}"

    def json(self):
        return self._payload


def test_all_ten_requested_automation_capabilities_have_runtime_entrypoints():
    # 1 claim collection, 2 inquiry+AI, 3/4 inventory state automation,
    # 5 settlement, 6 template install, 7 xlsx, 8 cross-market clone,
    # 9 GUI-backed scheduler persistence, 10 payment orchestration.
    assert callable(sync_claims)
    assert callable(sync_inquiries)
    assert callable(generate_ai_inquiry_draft)
    assert callable(run_inventory_automation)
    assert callable(sync_settlements)
    assert callable(install_channel_template_runtime)
    assert callable(apply_bulk_product_xlsx)
    assert callable(stage_marketplace_clone)
    assert callable(save_scheduler_rule)
    assert callable(prepare_payment)
    assert callable(sync_payment_sessions)


def test_naver_claim_collection_follows_more_cursor(monkeypatch):
    calls = []

    def fake_get(path, params):
        calls.append(dict(params))
        if len(calls) == 1:
            return FakeResponse({
                "data": {
                    "lastChangeStatuses": [
                        {
                            "orderId": "O1",
                            "productOrderId": "P1",
                            "claimType": "CANCEL",
                            "lastChangedType": "CLAIM_REQUESTED",
                        }
                    ],
                    "more": {
                        "moreFrom": "2026-08-28T10:00:00.000+09:00",
                        "moreSequence": 123,
                    },
                }
            })
        return FakeResponse({
            "data": {
                "lastChangeStatuses": [
                    {
                        "orderId": "O2",
                        "productOrderId": "P2",
                        "claimType": "RETURN",
                        "lastChangedType": "CLAIM_COMPLETED",
                    }
                ]
            }
        })

    monkeypatch.setattr(commerce_ops_api, "_naver_get", fake_get)
    rows = commerce_ops_api.collect_naver_claims(hours_back=24)

    assert [x["external_item_id"] for x in rows] == ["P1", "P2"]
    assert calls[1]["lastChangedFrom"] == "2026-08-28T10:00:00.000+09:00"
    assert calls[1]["moreSequence"] == 123


def test_coupang_inquiry_collection_reads_all_total_pages(monkeypatch):
    seen_pages = []

    class FakeCoupang:
        _vendor_id = "A000TEST"

        def _get(self, path):
            page = int(parse_qs(urlparse(path).query)["pageNum"][0])
            seen_pages.append(page)
            return FakeResponse({
                "data": {
                    "content": [
                        {
                            "inquiryId": page,
                            "content": f"q{page}",
                            "vendorItemId": 100 + page,
                            "commentDtoList": [],
                        }
                    ],
                    "pagination": {
                        "currentPage": page,
                        "totalPages": 2,
                        "totalElements": 2,
                        "countPerPage": 50,
                    },
                }
            })

    monkeypatch.setattr(commerce_ops_api, "get_coupang_uploader", lambda: FakeCoupang())
    rows = commerce_ops_api.collect_coupang_inquiries(days=7)

    assert seen_pages == [1, 2]
    assert [x["external_inquiry_id"] for x in rows] == ["1", "2"]


def test_naver_product_inquiry_collection_reads_declared_pages(monkeypatch):
    seen_pages = []

    def fake_get(path, params):
        page = int(params["page"])
        seen_pages.append(page)
        return FakeResponse({
            "contents": [
                {
                    "questionId": page,
                    "productId": 1000 + page,
                    "question": f"q{page}",
                    "answered": False,
                }
            ],
            "totalPages": 2,
        })

    monkeypatch.setattr(commerce_ops_api, "_naver_get", fake_get)
    rows = commerce_ops_api.collect_naver_inquiries()

    assert seen_pages == [1, 2]
    assert [x["external_inquiry_id"] for x in rows] == ["1", "2"]


def test_coupang_settlement_pagination_accepts_nested_data(monkeypatch):
    calls = []

    class FakeCoupang:
        _vendor_id = "A000TEST"

        def _get(self, path):
            calls.append(path)
            if len(calls) == 1:
                return FakeResponse({
                    "data": {
                        "items": [
                            {
                                "orderId": "O1",
                                "recognitionDate": "2026-08-27",
                                "saleType": "SALE",
                                "items": [{"vendorItemId": "V1", "saleAmount": 10000, "quantity": 1}],
                            }
                        ],
                        "hasNext": True,
                        "nextToken": "NEXT",
                    }
                })
            return FakeResponse({
                "data": {
                    "items": [
                        {
                            "orderId": "O2",
                            "recognitionDate": "2026-08-27",
                            "saleType": "SALE",
                            "items": [{"vendorItemId": "V2", "saleAmount": 20000, "quantity": 1}],
                        }
                    ],
                    "hasNext": False,
                }
            })

    monkeypatch.setattr(commerce_ops_api, "get_coupang_uploader", lambda: FakeCoupang())
    rows = commerce_ops_api.collect_coupang_settlements(days=2)

    assert len(rows) == 2
    assert "token=NEXT" in calls[1]
