from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class ThreadsConfig:
    user_id: str
    access_token: str
    app_secret: str
    verify_token: str
    graph_base_url: str = "https://graph.threads.net"

    @classmethod
    def from_env(cls) -> "ThreadsConfig":
        user_id = os.getenv("THREADS_USER_ID", "").strip()
        access_token = os.getenv("THREADS_ACCESS_TOKEN", "").strip()
        try:
            from app.social.threads.auth import active_credentials
            connected = active_credentials()
            if connected:
                user_id, access_token = connected
        except Exception:
            pass
        return cls(
            user_id=user_id,
            access_token=access_token,
            app_secret=os.getenv("THREADS_APP_SECRET", "").strip(),
            verify_token=os.getenv("THREADS_VERIFY_TOKEN", "").strip(),
            graph_base_url=os.getenv("THREADS_GRAPH_BASE_URL", "https://graph.threads.net").rstrip("/"),
        )


class ThreadsClient:
    def __init__(self, config: ThreadsConfig | None = None, timeout: float = 30.0) -> None:
        self.config = config or ThreadsConfig.from_env()
        self.timeout = timeout

    def _ensure_configured(self) -> None:
        if not self.config.user_id or not self.config.access_token:
            raise RuntimeError("Connect a Threads OAuth account or set THREADS_USER_ID / THREADS_ACCESS_TOKEN")

    def _url(self, path: str) -> str:
        return f"{self.config.graph_base_url}/{path.lstrip('/')}"

    def _auth(self) -> dict[str, str]:
        return {"access_token": self.config.access_token}

    def _create_container(self, payload: dict[str, Any]) -> str:
        self._ensure_configured()
        with httpx.Client(timeout=self.timeout) as client:
            created = client.post(self._url(f"{self.config.user_id}/threads"), data={**payload, **self._auth()})
            created.raise_for_status()
            return str(created.json()["id"])

    def _publish_container(self, creation_id: str) -> str:
        self._ensure_configured()
        with httpx.Client(timeout=self.timeout) as client:
            published = client.post(
                self._url(f"{self.config.user_id}/threads_publish"),
                data={"creation_id": creation_id, **self._auth()},
            )
            published.raise_for_status()
            return str(published.json()["id"])

    def publish_text(self, text: str, reply_to_id: str | None = None) -> str:
        payload: dict[str, Any] = {"media_type": "TEXT", "text": text}
        if reply_to_id:
            payload["reply_to_id"] = reply_to_id
        return self._publish_container(self._create_container(payload))

    def publish_image(self, image_url: str, text: str = "", alt_text: str = "", reply_to_id: str | None = None) -> str:
        if not image_url.startswith(("http://", "https://")):
            raise ValueError("Threads image_url must be a public HTTP(S) URL")
        payload: dict[str, Any] = {"media_type": "IMAGE", "image_url": image_url}
        if text:
            payload["text"] = text
        if alt_text:
            payload["alt_text"] = alt_text[:1000]
        if reply_to_id:
            payload["reply_to_id"] = reply_to_id
        return self._publish_container(self._create_container(payload))

    def publish_video(self, video_url: str, text: str = "", alt_text: str = "", reply_to_id: str | None = None) -> str:
        if not video_url.startswith(("http://", "https://")):
            raise ValueError("Threads video_url must be a public HTTP(S) URL")
        payload: dict[str, Any] = {"media_type": "VIDEO", "video_url": video_url}
        if text:
            payload["text"] = text
        if alt_text:
            payload["alt_text"] = alt_text[:1000]
        if reply_to_id:
            payload["reply_to_id"] = reply_to_id
        return self._publish_container(self._create_container(payload))

    def publish_carousel(self, items: list[dict[str, str]], text: str = "") -> str:
        if not 2 <= len(items) <= 20:
            raise ValueError("Threads carousel requires 2 to 20 items")
        child_ids: list[str] = []
        for item in items:
            media_type = str(item.get("media_type", "IMAGE")).upper()
            if media_type not in {"IMAGE", "VIDEO"}:
                raise ValueError("carousel media_type must be IMAGE or VIDEO")
            key = "image_url" if media_type == "IMAGE" else "video_url"
            url = str(item.get(key, ""))
            if not url.startswith(("http://", "https://")):
                raise ValueError(f"{key} must be a public HTTP(S) URL")
            payload: dict[str, Any] = {
                "media_type": media_type,
                key: url,
                "is_carousel_item": "true",
            }
            if item.get("alt_text"):
                payload["alt_text"] = str(item["alt_text"])[:1000]
            child_ids.append(self._create_container(payload))
        parent = {"media_type": "CAROUSEL", "children": ",".join(child_ids)}
        if text:
            parent["text"] = text
        return self._publish_container(self._create_container(parent))

    def get_replies(self, post_id: str, limit: int = 50) -> list[dict[str, Any]]:
        self._ensure_configured()
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                self._url(f"{post_id}/replies"),
                params={
                    "fields": "id,text,username,timestamp",
                    "limit": max(1, min(limit, 100)),
                    **self._auth(),
                },
            )
            response.raise_for_status()
            return list(response.json().get("data", []))


def verify_webhook_signature(raw_body: bytes, signature_header: str | None, app_secret: str) -> bool:
    if not app_secret:
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    supplied = signature_header.split("=", 1)[1]
    return hmac.compare_digest(expected, supplied)
