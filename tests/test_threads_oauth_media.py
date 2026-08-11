from cryptography.fernet import Fernet

from app.social.threads.auth import decrypt_token, encrypt_token
from app.social.threads.client import ThreadsClient, ThreadsConfig


def test_token_round_trip(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("THREADS_TOKEN_ENCRYPTION_KEY", key)
    token = "secret-threads-token"
    encrypted = encrypt_token(token)
    assert encrypted != token
    assert decrypt_token(encrypted) == token


def test_publish_carousel_builds_children_and_parent(monkeypatch):
    cfg = ThreadsConfig(
        user_id="user1",
        access_token="token",
        app_secret="secret",
        verify_token="verify",
        graph_base_url="https://graph.threads.net",
    )
    client = ThreadsClient(cfg)
    created = []

    def fake_create(payload):
        created.append(payload)
        return f"container-{len(created)}"

    monkeypatch.setattr(client, "_create_container", fake_create)
    monkeypatch.setattr(client, "_publish_container", lambda cid: f"published-{cid}")

    result = client.publish_carousel([
        {"media_type": "IMAGE", "image_url": "https://example.com/a.jpg"},
        {"media_type": "VIDEO", "video_url": "https://example.com/b.mp4"},
    ], "hello")

    assert result == "published-container-3"
    assert created[0]["is_carousel_item"] == "true"
    assert created[1]["is_carousel_item"] == "true"
    assert created[2]["media_type"] == "CAROUSEL"
    assert created[2]["children"] == "container-1,container-2"
