from __future__ import annotations

from pathlib import Path

import httpx

from app.media.ai_detail_page import _request_image


def _response(status: int, payload: dict, url: str = "https://api.openai.com/v1/images/edits") -> httpx.Response:
    return httpx.Response(status, json=payload, request=httpx.Request("POST", url))


def test_gpt_image_2_reference_edit_omits_unsupported_input_fidelity(monkeypatch):
    calls: list[dict] = []

    def fake_post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return _response(200, {"data": [{"b64_json": "ZmFrZQ=="}]}, url)

    monkeypatch.setattr("app.media.ai_detail_page.httpx.post", fake_post)

    response = _request_image(
        headers={"Authorization": "Bearer test"},
        model="gpt-image-2",
        prompt="CI 차량용 청소기 상품 썸네일",
        size="1024x1024",
        quality="medium",
        ref=(b"fake-image", ".png"),
    )

    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0]["url"].endswith("/v1/images/edits")
    assert calls[0]["data"]["model"] == "gpt-image-2"
    assert "input_fidelity" not in calls[0]["data"]


def test_input_fidelity_capability_error_retries_without_parameter(monkeypatch):
    calls: list[dict] = []

    def fake_post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        if len(calls) == 1:
            return _response(
                400,
                {
                    "error": {
                        "message": "The model does not support the input_fidelity parameter.",
                        "code": "invalid_input_fidelity_model",
                    }
                },
                url,
            )
        return _response(200, {"data": [{"b64_json": "ZmFrZQ=="}]}, url)

    monkeypatch.setattr("app.media.ai_detail_page.httpx.post", fake_post)

    response = _request_image(
        headers={"Authorization": "Bearer test"},
        model="gpt-image-1.5",
        prompt="reference edit",
        size="1024x1024",
        quality="medium",
        ref=(b"fake-image", ".jpg"),
    )

    assert response.status_code == 200
    assert len(calls) == 2
    assert calls[0]["data"]["input_fidelity"] == "high"
    assert "input_fidelity" not in calls[1]["data"]


def test_no_streamlit_page_links_target_removed_app_py_entrypoint():
    root = Path(__file__).resolve().parents[1]
    stale: list[str] = []
    for path in (root / "gui" / "pages").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if 'page_link("app.py"' in text or "page_link('app.py'" in text:
            stale.append(path.name)

    assert stale == []


def test_threads_home_link_targets_main_entrypoint():
    root = Path(__file__).resolve().parents[1]
    page = (root / "gui/pages/10_Social_Commerce_Threads.py").read_text(encoding="utf-8")
    assert 'page_link("main.py", label="통합 판매 홈"' in page
