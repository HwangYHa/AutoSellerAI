from __future__ import annotations

from app.platforms.coupang import CoupangUploader


class _Resp:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


def _uploader() -> CoupangUploader:
    return object.__new__(CoupangUploader)


def test_explicit_valid_category_is_reused(monkeypatch):
    uploader = _uploader()
    monkeypatch.setattr(uploader, "_category_is_valid", lambda code: str(code) == "77777")
    monkeypatch.setattr(uploader, "_recommend_category", lambda product: (_ for _ in ()).throw(AssertionError("recommend should not run")))

    code, name = uploader._resolve_display_category({
        "name": "테스트 상품",
        "display_category_code": "77777",
    })

    assert code == "77777"
    assert name == ""


def test_invalid_explicit_category_falls_back_to_live_recommendation(monkeypatch):
    uploader = _uploader()
    monkeypatch.setattr(uploader, "_category_is_valid", lambda code: False)
    monkeypatch.setattr(uploader, "_recommend_category", lambda product: ("88888", "추천 카테고리"))

    code, name = uploader._resolve_display_category({
        "name": "국내산 한우사골육수 400g 완조리 국물요리 육수팩",
        "display_category_code": "56101",
        "category": "식품",
    })

    assert code == "88888"
    assert name == "추천 카테고리"


def test_text_category_never_uses_old_hardcoded_default(monkeypatch):
    uploader = _uploader()
    monkeypatch.setattr(uploader, "_recommend_category", lambda product: ("99999", "육수"))

    code, name = uploader._resolve_display_category({
        "name": "국내산 한우사골육수 400g",
        "category": "식품 > 국/탕/찌개 > 육수",
    })

    assert code == "99999"
    assert code != "56101"
    assert name == "육수"


def test_recommend_category_validates_predicted_category(monkeypatch):
    uploader = _uploader()

    def fake_post(path, body):
        assert path.endswith("/categorization/predict")
        assert body["productName"] == "국내산 한우사골육수 400g"
        return _Resp(200, {
            "code": 200,
            "message": "OK",
            "data": {
                "autoCategorizationPredictionResultType": "SUCCESS",
                "predictedCategoryId": "12345",
                "predictedCategoryName": "육수",
                "comment": None,
            },
        })

    monkeypatch.setattr(uploader, "_post", fake_post)
    monkeypatch.setattr(uploader, "_category_is_valid", lambda code: str(code) == "12345")

    code, name = uploader._recommend_category({
        "name": "국내산 한우사골육수 400g",
        "category": "식품",
        "origin": "대한민국",
    })

    assert code == "12345"
    assert name == "육수"
