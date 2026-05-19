"""Paymo scoring API klienti.

Hujjat: karta bo'yicha 12 oylik tushumlar (kredit skoring uchun).
Endpoint: GET https://api.paymo.uz/scoring/score/by-token/{card_token}
Auth: statik Bearer token (PAYMO_AUTH_TOKEN .env'da).
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)


class PaymoError(RuntimeError):
    """Paymo API ishlamadi (tarmoq xatosi yoki noto'g'ri javob)."""


class PaymoBusinessError(PaymoError):
    """Paymo biznes-mantiq xatosi (result.code != 'OK')."""

    def __init__(self, code: Any, description: str | None = None):
        self.code = code
        self.description = description or ""
        super().__init__(f"Paymo error {code}: {description}")


class PaymoClient:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.PAYMO_BASE_URL or "https://api.paymo.uz",
            timeout=float(settings.PAYMO_TIMEOUT or 20),
        )

    def _auth_header(self) -> dict[str, str]:
        token = settings.PAYMO_AUTH_TOKEN
        if not token:
            raise PaymoError("PAYMO_AUTH_TOKEN .env'da yo'q")
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    async def get_card_scoring(self, card_token: str) -> dict[str, Any]:
        """GET /scoring/score/by-token/{card_token} — 12 oylik tushum tarixi."""
        if not card_token:
            raise PaymoError("card_token bo'sh bo'lishi mumkin emas")
        path = f"/scoring/score/by-token/{card_token}"
        try:
            r = await self._client.get(path, headers=self._auth_header())
        except httpx.HTTPError as e:
            raise PaymoError(f"Paymo {path}: tarmoq xatosi ({e})") from e
        if r.status_code == 401:
            raise PaymoError("Paymo 401: PAYMO_AUTH_TOKEN noto'g'ri yoki muddati o'tgan")
        if r.status_code == 404:
            raise PaymoBusinessError("NOT_FOUND", "Karta topilmadi yoki token noto'g'ri")
        if r.status_code != 200:
            raise PaymoError(f"Paymo {path} {r.status_code}: {r.text}")
        try:
            data = r.json()
        except ValueError:
            raise PaymoError(f"Paymo {path}: JSON parse xatosi ({r.text!r})")
        self._raise_if_business_error(data)
        return data

    @staticmethod
    def _raise_if_business_error(data: dict[str, Any]) -> None:
        result = (data or {}).get("result") or {}
        code = result.get("code")
        if code is None:
            return
        if str(code).upper() == "OK" or str(code) == "0":
            return
        raise PaymoBusinessError(code, result.get("description"))

    async def aclose(self) -> None:
        await self._client.aclose()


paymo = PaymoClient()
