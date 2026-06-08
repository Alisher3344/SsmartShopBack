"""MyID Mobile SDK (new flow) klient — Flutter native biometric oqim uchun.

Doc: https://docs.myid.uz/ru/sdknew.md

New flow farqi (eski klassik SDK'dan):
  - Backend avval `/api/v1/auth/clients/access-token` orqali **klient tokeni**
    oladi (faqat `client_id` + `client_secret`). Token cache qilinadi.
  - Keyin `/api/v2/sdk/sessions` chaqirib `session_id` yaratadi (passport/pinfl
    oldindan beriladi → SDK form'ni o'tkazib yuboradi).
  - Mobile SDK shu `session_id` bilan ishga tushadi va `code` qaytaradi.
  - Backend `GET /api/v1/sdk/data?code=...` orqali foydalanuvchi ma'lumotlarini
    oladi. `users/me` chaqirig'i yo'q.

Flow (overview):
  1. Mobile → backend: POST /api/mobile/auth/myid/session {pinfl?, ...}
  2. Backend → MyID:   POST /api/v1/auth/clients/access-token  (cached)
                      → POST /api/v2/sdk/sessions  → session_id
  3. Backend → Mobile: {session_id}
  4. Mobile → SDK.initialize(session_id) → yuz skan → code
  5. Mobile → backend: POST /api/mobile/auth/myid/verify {code}
  6. Backend → MyID:   GET /api/v1/sdk/data?code=...  → profile + reuid
  7. Backend → Mobile: {access_token, user}
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from app.core.config import settings
from app.core.myid import MyIDError, MyIDOAuthClient

log = logging.getLogger(__name__)


class MyIDSDKClient:
    """`api.devmyid.uz` / `api.myid.uz` SDK new flow uchun klient."""

    # Token kechiktirilgan eskirish (server vaqt farqi uchun)
    _TOKEN_TTL_SKEW = 30  # soniyada

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.MYID_SDK_BASE_URL,
            timeout=15.0,
        )
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()

    async def _get_client_token(self) -> str:
        """Cached client access_token — `expires_in` muddatiga qadar saqlanadi."""
        if self._token and time.monotonic() < self._token_expires_at:
            return self._token

        async with self._token_lock:
            # Boshqa task allaqachon yangilagan bo'lishi mumkin
            if self._token and time.monotonic() < self._token_expires_at:
                return self._token

            if not settings.MYID_SDK_CLIENT_ID or not settings.MYID_SDK_CLIENT_SECRET:
                raise MyIDError("MYID_SDK_CLIENT_ID/SECRET .env'da yo'q")

            try:
                r = await self._client.post(
                    "/api/v1/auth/clients/access-token",
                    json={
                        "client_id": settings.MYID_SDK_CLIENT_ID,
                        "client_secret": settings.MYID_SDK_CLIENT_SECRET,
                    },
                    headers={"Accept": "application/json"},
                )
            except httpx.HTTPError as e:
                raise MyIDError(f"MyID SDK access-token: tarmoq xatosi ({e})") from e

            data = MyIDOAuthClient._parse(r, "sdk/clients/access-token")
            token = data.get("access_token")
            expires_in = data.get("expires_in")
            if not token:
                raise MyIDError(f"MyID SDK access-token: token yo'q ({data!r})")
            try:
                ttl = int(expires_in) if expires_in is not None else 3600
            except (TypeError, ValueError):
                ttl = 3600
            self._token = token
            self._token_expires_at = time.monotonic() + max(60, ttl - self._TOKEN_TTL_SKEW)
            return token

    async def create_session(
        self,
        *,
        pinfl: str | None = None,
        pass_data: str | None = None,
        phone_number: str | None = None,
        birth_date: str | None = None,
        is_resident: bool | None = None,
        threshold: float | None = None,
        reuid: str | None = None,
    ) -> dict[str, Any]:
        """SDK session yaratish — `session_id` qaytaradi.

        Doc: POST /api/v2/sdk/sessions
        - Variant A (PINFL): {pinfl, phone_number, birth_date, is_resident, threshold}
        - Variant B (passport): {pass_data, phone_number, birth_date, is_resident, threshold}
        - Variant C (bo'sh):   {} — SDK form ko'rsatadi
        - Variant D (reuid):   {reuid, phone_number?, threshold?}

        Faqat berilgan maydonlar payload'ga qo'shiladi. `birth_date` ISO format
        (`YYYY-MM-DD`) bo'lishi kerak — MyID `DD.MM.YYYY`'ni qabul qilmaydi.
        """
        token = await self._get_client_token()
        payload: dict[str, Any] = {}
        if reuid:
            payload["reuid"] = reuid
        elif pinfl:
            payload["pinfl"] = pinfl
        elif pass_data:
            payload["pass_data"] = pass_data
        if phone_number:
            payload["phone_number"] = phone_number
        if birth_date:
            payload["birth_date"] = birth_date
        if is_resident is not None:
            payload["is_resident"] = is_resident
        if threshold is not None:
            payload["threshold"] = threshold

        try:
            r = await self._client.post(
                "/api/v2/sdk/sessions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
            )
        except httpx.HTTPError as e:
            raise MyIDError(f"MyID SDK sessions: tarmoq xatosi ({e})") from e
        return MyIDOAuthClient._parse(r, "sdk/sessions")

    async def get_sdk_data(self, code: str) -> dict[str, Any]:
        """SDK qaytargan `code`'ni foydalanuvchi ma'lumotlariga almashtirish.

        Doc: GET /api/v1/sdk/data?code=...

        Javob: `{data: {comparison_value, pass_data, job_id, profile: {...}}, reuid: {...}}`
        """
        token = await self._get_client_token()
        try:
            r = await self._client.get(
                "/api/v1/sdk/data",
                params={"code": code},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
                timeout=30.0,
            )
        except httpx.HTTPError as e:
            raise MyIDError(f"MyID SDK data: tarmoq xatosi ({e})") from e
        return MyIDOAuthClient._parse(r, "sdk/data")

    async def get_session(self, session_id: str) -> dict[str, Any]:
        """Session holatini tekshirish (qulashdan keyin code'ni qayta olish)."""
        token = await self._get_client_token()
        try:
            r = await self._client.get(
                f"/api/v1/sdk/sessions/{session_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
            )
        except httpx.HTTPError as e:
            raise MyIDError(f"MyID SDK session get: tarmoq xatosi ({e})") from e
        return MyIDOAuthClient._parse(r, f"sdk/sessions/{session_id}")

    async def aclose(self) -> None:
        await self._client.aclose()


myid_sdk = MyIDSDKClient()
