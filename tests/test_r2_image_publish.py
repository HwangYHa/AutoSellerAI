from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace

from app.media import ai_detail_page, r2_storage, thumbnail


class _FakeS3:
    def __init__(self):
        self.calls: list[dict] = []

    def put_object(self, **kwargs):
        body = kwargs["Body"]
        self.calls.append({**kwargs, "Body": body.read()})
        return {"ETag": '"test"'}


def _storage_settings(tmp_path: Path, **overrides):
    values = {
        "image_output_dir": str(tmp_path / "generated"),
        "image_public_base_url": "https://pub-test.r2.dev",
        "image_cdn_base_url": "",
        "r2_enabled": True,
        "r2_access_key_id": "test-access",
        "r2_secret_access_key": "test-secret",
        "r2_bucket": "autoseller-images",
        "r2_endpoint": "https://account.r2.cloudflarestorage.com",
        "r2_object_prefix": "generated",
        "r2_region": "auto",
        "r2_cache_control": "public, max-age=31536000, immutable",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_r2_upload_uses_generated_prefix_and_public_url(monkeypatch, tmp_path):
    settings = _storage_settings(tmp_path)
    target = tmp_path / "generated" / "thumbnails" / "sample.png"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"png-data")
    fake = _FakeS3()

    monkeypatch.setattr(r2_storage, "get_settings", lambda: settings)
    monkeypatch.setattr(r2_storage, "_build_client", lambda _settings: fake)

    public_url = r2_storage.publish_generated_file(target)

    assert public_url == "https://pub-test.r2.dev/generated/thumbnails/sample.png"
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["Bucket"] == "autoseller-images"
    assert call["Key"] == "generated/thumbnails/sample.png"
    assert call["Body"] == b"png-data"
    assert call["ContentType"] == "image/png"


def test_r2_public_base_may_already_include_prefix(monkeypatch, tmp_path):
    settings = _storage_settings(
        tmp_path,
        image_public_base_url="https://pub-test.r2.dev/generated",
    )
    target = tmp_path / "generated" / "detail.png"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"detail")
    fake = _FakeS3()

    monkeypatch.setattr(r2_storage, "get_settings", lambda: settings)
    monkeypatch.setattr(r2_storage, "_build_client", lambda _settings: fake)

    public_url = r2_storage.publish_generated_file(target)

    assert public_url == "https://pub-test.r2.dev/generated/detail.png"
    assert fake.calls[0]["Key"] == "generated/detail.png"


def test_r2_disabled_preserves_legacy_public_mapping(monkeypatch, tmp_path):
    settings = _storage_settings(
        tmp_path,
        r2_enabled=False,
        image_public_base_url="https://cdn.example.test/generated",
    )
    target = tmp_path / "generated" / "thumbnails" / "legacy.png"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"legacy")

    monkeypatch.setattr(r2_storage, "get_settings", lambda: settings)
    monkeypatch.setattr(
        r2_storage,
        "_build_client",
        lambda _settings: (_ for _ in ()).throw(AssertionError("R2 client must not be built")),
    )

    assert r2_storage.publish_generated_file(target) == "https://cdn.example.test/generated/thumbnails/legacy.png"


def test_thumbnail_generation_publishes_saved_file(monkeypatch, tmp_path):
    settings = SimpleNamespace(
        image_ai_enabled=True,
        image_ai_provider="openai",
        openai_api_key="test",
        image_ai_model="gpt-image-2",
        image_thumbnail_size="1024x1024",
        image_thumbnail_quality="medium",
        image_output_dir=str(tmp_path / "generated"),
    )

    class _Response:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {"data": [{"b64_json": base64.b64encode(b"thumbnail").decode()}]}

    published: list[Path] = []
    monkeypatch.setattr(thumbnail, "get_settings", lambda: settings)
    monkeypatch.setattr(thumbnail, "_download_reference", lambda _url: None)
    monkeypatch.setattr(thumbnail, "_request_image", lambda **_kwargs: _Response())
    monkeypatch.setattr(
        thumbnail,
        "publish_generated_file",
        lambda path: published.append(Path(path)) or "https://pub-test.r2.dev/generated/thumbnails/test.png",
    )

    result = thumbnail.generate_thumbnail({"sku": "SKU-1", "name": "테스트 상품"})

    assert published == [Path(result.local_path)]
    assert result.public_url.startswith("https://pub-test.r2.dev/generated/thumbnails/")
    assert Path(result.local_path).read_bytes() == b"thumbnail"


def test_detail_generation_publishes_saved_file(monkeypatch, tmp_path):
    settings = SimpleNamespace(
        image_ai_enabled=True,
        image_ai_provider="openai",
        openai_api_key="test",
        image_ai_model="gpt-image-2",
        image_ai_size="1024x1536",
        image_ai_quality="medium",
        image_ai_detail_count=1,
        image_output_dir=str(tmp_path / "generated"),
    )

    class _Response:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {"data": [{"b64_json": base64.b64encode(b"detail").decode()}]}

    published: list[Path] = []
    monkeypatch.setattr(ai_detail_page, "get_settings", lambda: settings)
    monkeypatch.setattr(ai_detail_page, "build_detail_prompts", lambda _product, count=1: [("hero", "prompt")])
    monkeypatch.setattr(ai_detail_page, "_download_reference", lambda _url: None)
    monkeypatch.setattr(ai_detail_page, "_request_image", lambda **_kwargs: _Response())
    monkeypatch.setattr(
        ai_detail_page,
        "publish_generated_file",
        lambda path: published.append(Path(path)) or "https://pub-test.r2.dev/generated/detail.png",
    )

    result = ai_detail_page.generate_detail_images({"sku": "SKU-2", "name": "상세 테스트"}, count=1)

    assert len(result) == 1
    assert published == [Path(result[0].local_path)]
    assert result[0].public_url == "https://pub-test.r2.dev/generated/detail.png"
    assert Path(result[0].local_path).read_bytes() == b"detail"
