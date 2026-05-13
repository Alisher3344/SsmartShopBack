"""Eskiz.uz SMS gateway klienti.

Token in-memory cache qilinadi; 401 javob kelganda avtomatik refresh.
Eskiz API: https://documenter.getpostman.com/view/663428/RzfmES4z
"""
from __future__ import annotations

import logging

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)


class EskizError(RuntimeError):
    pass


class EskizClient:
    def __init__(self) -> None:
        self._token: str | None = None
        self._client = httpx.AsyncClient(base_url=settings.ESKIZ_BASE_URL, timeout=15.0)

    async def _login(self) -> str:
        if not settings.ESKIZ_EMAIL or not settings.ESKIZ_PASSWORD:
            raise EskizError("ESKIZ_EMAIL/ESKIZ_PASSWORD .env da yo'q")
        r = await self._client.post(
            "/auth/login",
            data={"email": settings.ESKIZ_EMAIL, "password": settings.ESKIZ_PASSWORD},
        )
        if r.status_code != 200:
            raise EskizError(f"Eskiz login {r.status_code}: {r.text}")
        token = (r.json() or {}).get("data", {}).get("token")
        if not token:
            raise EskizError(f"Eskiz login: token yo'q ({r.text})")
        self._token = token
        return token

    async def _ensure_token(self) -> str:
        return self._token or await self._login()

    async def send_sms(self, phone: str, message: str) -> dict:
        """phone: prefiksiz xalqaro format, masalan '998901234567'."""
        for attempt in (1, 2):
            token = await self._ensure_token()
            r = await self._client.post(
                "/message/sms/send",
                headers={"Authorization": f"Bearer {token}"},
                data={
                    "mobile_phone": phone,
                    "message": message,
                    "from": settings.ESKIZ_SENDER_NICK,
                },
            )
            if r.status_code == 401 and attempt == 1:
                self._token = None
                continue
            if r.status_code not in (200, 201):
                raise EskizError(f"Eskiz send {r.status_code}: {r.text}")
            return r.json()
        raise EskizError("Eskiz send: takrorlanuvchi xato")

    async def aclose(self) -> None:
        await self._client.aclose()


eskiz = EskizClient()
