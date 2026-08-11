from __future__ import annotations

import base64
import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import desc, select

from app.db import get_db, init_db
from app.social.threads.auth_models import ThreadsCredential

GRAPH = "https://graph.threads.net"
AUTHORIZE = "https://threads.net/oauth/authorize"
DEFAULT_SCOPES = [
    "threads_basic",
    "threads_content_publish",
    "threads_read_replies",
    "threads_manage_replies",
    "threads_manage_insights",
]


@dataclass(frozen=True)
class OAuthConfig:
    app_id: str
    app_secret: str
    redirect_uri: str
    encryption_key: str

    @classmethod
    def from_env(cls) -> "OAuthConfig":
        return cls(
            app_id=os.getenv("THREADS_APP_ID", "").strip(),
            app_secret=os.getenv("THREADS_APP_SECRET", "").strip(),
            redirect_uri=os.getenv("THREADS_OAUTH_REDIRECT_URI", "").strip(),
            encryption_key=os.getenv("THREADS_TOKEN_ENCRYPTION_KEY", "").strip(),
        )

    def validate(self) -> None:
        missing = [
            name for name, value in (
                ("THREADS_APP_ID", self.app_id),
                ("THREADS_APP_SECRET", self.app_secret),
                ("THREADS_OAUTH_REDIRECT_URI", self.redirect_uri),
                ("THREADS_TOKEN_ENCRYPTION_KEY", self.encryption_key),
            ) if not value
        ]
        if missing:
            raise RuntimeError("missing Threads OAuth settings: " + ", ".join(missing))


def generate_fernet_key() -> str:
    return Fernet.generate_key().decode("ascii")


def _fernet() -> Fernet:
    key = OAuthConfig.from_env().encryption_key
    if not key:
        raise RuntimeError("THREADS_TOKEN_ENCRYPTION_KEY is required")
    try:
        return Fernet(key.encode("ascii"))
    except Exception as exc:
        raise RuntimeError("THREADS_TOKEN_ENCRYPTION_KEY must be a valid Fernet key") from exc


def encrypt_token(token: str) -> str:
    return _fernet().encrypt(token.encode("utf-8")).decode("ascii")


def decrypt_token(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("unable to decrypt stored Threads token") from exc


def build_authorization_url(state: str | None = None, scopes: list[str] | None = None) -> tuple[str, str]:
    cfg = OAuthConfig.from_env()
    cfg.validate()
    state = state or secrets.token_urlsafe(24)
    params = {
        "client_id": cfg.app_id,
        "redirect_uri": cfg.redirect_uri,
        "scope": ",".join(scopes or DEFAULT_SCOPES),
        "response_type": "code",
        "state": state,
    }
    return f"{AUTHORIZE}?{urlencode(params)}", state


def exchange_code(code: str) -> dict:
    cfg = OAuthConfig.from_env()
    cfg.validate()
    response = httpx.post(
        f"{GRAPH}/oauth/access_token",
        params={
            "client_id": cfg.app_id,
            "client_secret": cfg.app_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": cfg.redirect_uri,
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def exchange_long_lived(short_lived_token: str) -> dict:
    cfg = OAuthConfig.from_env()
    cfg.validate()
    response = httpx.get(
        f"{GRAPH}/access_token",
        params={
            "grant_type": "th_exchange_token",
            "client_secret": cfg.app_secret,
            "access_token": short_lived_token,
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def refresh_long_lived(access_token: str) -> dict:
    response = httpx.get(
        f"{GRAPH}/refresh_access_token",
        params={"grant_type": "th_refresh_token", "access_token": access_token},
        timeout=20,
    )
    response.raise_for_status()
    data = response.json() if response.content else {}
    # Some API clients/documentation omit the sample response. Preserve the
    # existing token if Meta returns no replacement while still considering
    # the successful refresh request.
    if not data.get("access_token"):
        data["access_token"] = access_token
    if not data.get("expires_in"):
        data["expires_in"] = 60 * 24 * 60 * 60
    return data


def fetch_profile(access_token: str) -> dict:
    response = httpx.get(
        f"{GRAPH}/me",
        params={"fields": "id,username,threads_profile_picture_url", "access_token": access_token},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def save_long_lived_credential(user_id: str, token: str, expires_in: int, username: str = "", scopes: str = "") -> ThreadsCredential:
    init_db()
    now = datetime.utcnow()
    expires_at = now + timedelta(seconds=max(int(expires_in or 0), 60))
    with get_db() as db:
        row = db.scalar(select(ThreadsCredential).where(ThreadsCredential.threads_user_id == str(user_id)))
        if not row:
            row = ThreadsCredential(
                threads_user_id=str(user_id),
                username=username,
                access_token_encrypted=encrypt_token(token),
                scopes=scopes,
            )
            db.add(row)
        else:
            row.username = username or row.username
            row.access_token_encrypted = encrypt_token(token)
            row.scopes = scopes or row.scopes
        row.status = "active"
        row.token_type = "bearer"
        row.issued_at = now
        row.expires_at = expires_at
        row.refreshed_at = now
        row.last_error = ""
        db.commit()
        db.refresh(row)
        db.expunge(row)
        return row


def complete_oauth(code: str) -> dict:
    short = exchange_code(code)
    short_token = str(short["access_token"])
    user_id = str(short.get("user_id", ""))
    long = exchange_long_lived(short_token)
    token = str(long["access_token"])
    expires_in = int(long.get("expires_in", 60 * 24 * 60 * 60))
    profile = fetch_profile(token)
    user_id = str(profile.get("id") or user_id)
    username = str(profile.get("username", ""))
    row = save_long_lived_credential(user_id, token, expires_in, username=username, scopes=",".join(DEFAULT_SCOPES))
    return credential_status(row.id)


def latest_credential() -> ThreadsCredential | None:
    init_db()
    with get_db() as db:
        row = db.scalar(select(ThreadsCredential).order_by(desc(ThreadsCredential.updated_at)).limit(1))
        if row:
            db.expunge(row)
        return row


def active_credentials() -> tuple[str, str] | None:
    row = latest_credential()
    if row and row.status == "active":
        if row.expires_at and row.expires_at <= datetime.utcnow():
            return None
        return row.threads_user_id, decrypt_token(row.access_token_encrypted)
    env_user = os.getenv("THREADS_USER_ID", "").strip()
    env_token = os.getenv("THREADS_ACCESS_TOKEN", "").strip()
    if env_user and env_token:
        return env_user, env_token
    return None


def refresh_stored_credential(credential_id: int | None = None) -> dict:
    init_db()
    with get_db() as db:
        if credential_id:
            row = db.get(ThreadsCredential, credential_id)
        else:
            row = db.scalar(select(ThreadsCredential).order_by(desc(ThreadsCredential.updated_at)).limit(1))
        if not row:
            raise RuntimeError("connected Threads credential not found")
        row_id = row.id
        token = decrypt_token(row.access_token_encrypted)
    try:
        data = refresh_long_lived(token)
        new_token = str(data.get("access_token", token))
        expires_in = int(data.get("expires_in", 60 * 24 * 60 * 60))
        with get_db() as db:
            row = db.get(ThreadsCredential, row_id)
            row.access_token_encrypted = encrypt_token(new_token)
            row.expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            row.refreshed_at = datetime.utcnow()
            row.status = "active"
            row.last_error = ""
            db.commit()
        return credential_status(row_id)
    except Exception as exc:
        with get_db() as db:
            row = db.get(ThreadsCredential, row_id)
            if row:
                row.last_error = str(exc)[:1000]
                row.status = "error"
                db.commit()
        raise


def credential_status(credential_id: int | None = None) -> dict:
    init_db()
    with get_db() as db:
        row = db.get(ThreadsCredential, credential_id) if credential_id else db.scalar(
            select(ThreadsCredential).order_by(desc(ThreadsCredential.updated_at)).limit(1)
        )
        if not row:
            return {"connected": False}
        now = datetime.utcnow()
        remaining = int((row.expires_at - now).total_seconds() // 86400) if row.expires_at else None
        return {
            "connected": row.status == "active" and (row.expires_at is None or row.expires_at > now),
            "id": row.id,
            "threads_user_id": row.threads_user_id,
            "username": row.username,
            "status": row.status,
            "issued_at": row.issued_at.isoformat() if row.issued_at else None,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "refreshed_at": row.refreshed_at.isoformat() if row.refreshed_at else None,
            "days_remaining": remaining,
            "last_error": row.last_error,
            "scopes": row.scopes,
        }
