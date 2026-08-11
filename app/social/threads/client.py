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
    graph_base_url: str = "https://graph.threads.net/v1.0"

    @classmethod
    def from_env(cls) -> "ThreadsConfig":
        return cls(
            user_id=os.getenv("THREADS_USER_ID", ""),
            access_token=os.getenv("THREADS_ACCESS_TOKEN", ""),
            app_secret=os.getenv("THREADS_APP_SECRET", ""),
            verify_token=os.getenv("THREADS_VERIFY_TOKEN", ""),
            graph_base_url=os.getenv("THREADS_GRAPH_BASE_URL", "https://graph.threads.net/v1.0").rstrip("/"),
        )


class ThreadsClient:
    def __init__(self, config: ThreadsConfig | None = None, timeout: float = 20.0) -> None:
        self.config = config or ThreadsConfig.from_env()
        self.timeout = timeout

    def _ensure_configured(self) -> None:
        if not self.config.user_id or not self.config.access_token:
            raise RuntimeError("THREADS_USER_ID and THREADS_ACCESS_TOKEN are required")

    def _url(self, path: str) -> str:
        return f"{self.config.graph_base_url}/{path.lstrip('/')}"

    def _auth(self) -> dict[str, str]:
        return {"access_token": self.config.access_token}

    def publish_text(self, text: str, reply_to_id: str | None = None) -> str:
        self._ensure_configured()
        payload: dict[str, Any] = {"media_type": "TEXT", "text": text, **self._auth()}
        if reply_to_id:
            payload["reply_to_id"] = reply_to_id

        with httpx.Client(timeout=self.timeout) as client:
            created = client.post(self._url(f"{self.config.user_id}/threads"), data=payload)
            created.raise_for_status()
            creation_id = str(created.json()["id"])

            published = client.post(
                self._url(f"{self.config.user_id}/threads_publish"),
                data={"creation_id": creation_id, **self._auth()},
            )
            published.raise_for_status()
            return str(published.json()["id"])

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
