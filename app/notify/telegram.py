"""Telegram Bot API — 동기 클라이언트 (requests 기반, Streamlit 호환)."""
from __future__ import annotations
import logging
import time
import requests

logger = logging.getLogger(__name__)

_SEND_URL = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramBot:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self._enabled = bool(token and chat_id)

    def is_enabled(self) -> bool:
        return self._enabled

    def send_message(self, text: str, parse_mode: str = "HTML") -> dict:
        """텍스트 메시지 발송. 성공 시 {"ok": True, ...}, 실패 시 {"ok": False, "error": str}."""
        if not self._enabled:
            return {"ok": False, "error": "Telegram 미설정 (BOT_TOKEN/CHAT_ID 확인)"}

        # Telegram HTML 최대 4096자 제한
        text = text[:4000] + "…" if len(text) > 4000 else text

        try:
            resp = requests.post(
                _SEND_URL.format(token=self.token),
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": True,
                },
                timeout=10,
            )
            data = resp.json()
            if not data.get("ok"):
                err = data.get("description", "Unknown error")
                logger.warning("Telegram 발송 실패: %s", err)
                return {"ok": False, "error": err}
            return {"ok": True, "message_id": data.get("result", {}).get("message_id")}
        except requests.exceptions.Timeout:
            return {"ok": False, "error": "요청 타임아웃 (10s)"}
        except Exception as exc:
            logger.error("Telegram 예외: %s", exc)
            return {"ok": False, "error": str(exc)}

    def send_photo(self, photo_url: str, caption: str = "") -> dict:
        """이미지 + 캡션 발송 (필요 시 확장)."""
        if not self._enabled:
            return {"ok": False, "error": "Telegram 미설정"}
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{self.token}/sendPhoto",
                json={
                    "chat_id": self.chat_id,
                    "photo": photo_url,
                    "caption": caption[:1024],
                    "parse_mode": "HTML",
                },
                timeout=10,
            )
            data = resp.json()
            return {"ok": data.get("ok", False), "error": data.get("description", "")}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def test_connection(self) -> dict:
        """연결 테스트 — getMe + 테스트 메시지 발송."""
        if not self._enabled:
            return {"ok": False, "error": "BOT_TOKEN 또는 CHAT_ID 미설정"}
        try:
            me = requests.get(
                f"https://api.telegram.org/bot{self.token}/getMe",
                timeout=10,
            ).json()
            if not me.get("ok"):
                return {"ok": False, "error": f"Bot 인증 실패: {me.get('description')}"}
            bot_name = me["result"].get("username", "?")
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

        result = self.send_message(
            f"✅ <b>AutoSeller AI 연결 테스트</b>\n"
            f"봇 <code>@{bot_name}</code> → Chat <code>{self.chat_id}</code>\n"
            f"알림 시스템 정상 작동 중입니다."
        )
        result["bot_name"] = bot_name
        return result


_bot_instance: TelegramBot | None = None


def get_bot() -> TelegramBot:
    """싱글톤 Bot 인스턴스를 반환한다."""
    global _bot_instance
    if _bot_instance is None:
        from app.config import get_settings
        s = get_settings()
        _bot_instance = TelegramBot(
            token=getattr(s, "telegram_bot_token", ""),
            chat_id=getattr(s, "telegram_chat_id", ""),
        )
    return _bot_instance
