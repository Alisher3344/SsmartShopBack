"""Atmos payment gateway klienti.

Hujjat: https://docs.atmos.uz

Token cache in-memory; 401 javob kelganda avtomatik refresh (Eskiz uslubida).
Pul birligi: TIYIN (1 so'm = 100 tiyin) — barcha amount field'lari tiyinda.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from typing import Any

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)


class AtmosError(RuntimeError):
    """Atmos API ishlamadi (tarmoq xatosi yoki noto'g'ri javob)."""


class AtmosBusinessError(AtmosError):
    """Atmos biznes-mantiq xatosi (e.g. -106 mablag' yetmaydi)."""

    def __init__(self, code: Any, description: str | None = None):
        self.code = code
        self.description = description or ""
        super().__init__(f"Atmos error {code}: {description}")


class AtmosClient:
    def __init__(self) -> None:
        self._token: str | None = None
        self._client = httpx.AsyncClient(
            base_url=settings.ATMOS_BASE_URL or "https://apigw.atmos.uz",
            timeout=20.0,
        )

    # ===== Auth =====

    async def _login(self) -> str:
        key = settings.ATMOS_CONSUMER_KEY
        secret = settings.ATMOS_CONSUMER_SECRET
        if not key or not secret:
            raise AtmosError("ATMOS_CONSUMER_KEY/ATMOS_CONSUMER_SECRET .env'da yo'q")
        basic = base64.b64encode(f"{key}:{secret}".encode()).decode()
        r = await self._client.post(
            "/token",
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials"},
        )
        if r.status_code != 200:
            raise AtmosError(f"Atmos token {r.status_code}: {r.text}")
        token = (r.json() or {}).get("access_token")
        if not token:
            raise AtmosError(f"Atmos token: access_token yo'q ({r.text})")
        self._token = token
        return token

    async def _ensure_token(self) -> str:
        return self._token or await self._login()

    # ===== Internal POST helper =====

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """JSON POST + 401'da bir marta refresh."""
        for attempt in (1, 2):
            token = await self._ensure_token()
            r = await self._client.post(
                path,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=payload,
            )
            if r.status_code == 401 and attempt == 1:
                self._token = None
                continue
            if r.status_code not in (200, 201):
                raise AtmosError(f"Atmos {path} {r.status_code}: {r.text}")
            try:
                data = r.json()
            except ValueError:
                raise AtmosError(f"Atmos {path}: JSON parse xatosi ({r.text!r})")
            self._raise_if_business_error(data)
            return data
        raise AtmosError(f"Atmos {path}: takrorlanuvchi auth xatosi")

    @staticmethod
    def _raise_if_business_error(data: dict[str, Any]) -> None:
        """Atmos javobida result.code != 'OK' bo'lsa biznes xato."""
        result = (data or {}).get("result") or {}
        code = result.get("code")
        if code is None:
            return
        # 'OK' yoki '0' (raqamli muvaffaqiyat) — xato emas
        if str(code).upper() == "OK" or str(code) == "0":
            return
        raise AtmosBusinessError(code, result.get("description"))

    # ===== Payment flow =====

    async def create_transaction(
        self,
        amount_tiyin: int,
        account: str,
        *,
        lang: str | None = None,
    ) -> dict[str, Any]:
        """POST /merchant/pay/create — qoralama tranzaksiya yaratish."""
        payload: dict[str, Any] = {
            "amount": amount_tiyin,
            "account": account,
            "store_id": settings.ATMOS_STORE_ID,
            "lang": lang or settings.ATMOS_DEFAULT_LANG,
        }
        if settings.ATMOS_TERMINAL_ID:
            payload["terminal_id"] = settings.ATMOS_TERMINAL_ID
        return await self._post("/merchant/pay/create", payload)

    async def pre_apply(
        self,
        transaction_id: int,
        card_number: str,
        expiry: str,
    ) -> dict[str, Any]:
        """POST /merchant/pay/pre-apply — karta raqami orqali.
        `expiry` formati: 'YYMM' (e.g. '2801' = yanvar 2028)."""
        payload = {
            "card_number": card_number,
            "expiry": expiry,
            "store_id": settings.ATMOS_STORE_ID,
            "transaction_id": transaction_id,
        }
        return await self._post("/merchant/pay/pre-apply", payload)

    async def pre_apply_token(
        self, transaction_id: int, card_token: str
    ) -> dict[str, Any]:
        """POST /merchant/pay/pre-apply — biriktirilgan karta token orqali."""
        payload = {
            "card_token": card_token,
            "store_id": settings.ATMOS_STORE_ID,
            "transaction_id": transaction_id,
        }
        return await self._post("/merchant/pay/pre-apply", payload)

    async def apply(self, transaction_id: int, otp: str) -> dict[str, Any]:
        """POST /merchant/pay/apply — OTP bilan yakuniy tasdiqlash."""
        payload = {
            "transaction_id": transaction_id,
            "otp": otp,
            "store_id": settings.ATMOS_STORE_ID,
        }
        return await self._post("/merchant/pay/apply", payload)

    # ===== Refund =====

    async def reverse(self, success_trans_id: int) -> dict[str, Any]:
        """POST /merchant/pay/reverse — to'liq qaytarish (full refund)."""
        return await self._post(
            "/merchant/pay/reverse",
            {
                "store_id": settings.ATMOS_STORE_ID,
                "success_trans_id": success_trans_id,
            },
        )

    async def create_reverse_partial(
        self, success_trans_id: int, amount_tiyin: int
    ) -> dict[str, Any]:
        """POST /merchant/pay/create-reverse-partial — qisman refund qoralamasi."""
        return await self._post(
            "/merchant/pay/create-reverse-partial",
            {
                "store_id": settings.ATMOS_STORE_ID,
                "success_trans_id": success_trans_id,
                "amount": amount_tiyin,
            },
        )

    async def confirm_reverse_partial(
        self, success_trans_id: int, reverse_id: int
    ) -> dict[str, Any]:
        """POST /merchant/pay/confirm-reverse-partial — qisman refund tasdig'i."""
        return await self._post(
            "/merchant/pay/confirm-reverse-partial",
            {
                "store_id": settings.ATMOS_STORE_ID,
                "success_trans_id": success_trans_id,
                "reverse_id": reverse_id,
            },
        )

    # ===== Bind card (saved cards) =====

    async def bind_card_init(self, card_number: str, expiry: str) -> dict[str, Any]:
        """POST /partner/bind-card/init — karta biriktirish arizasi."""
        return await self._post(
            "/partner/bind-card/init",
            {"card_number": card_number, "expiry": expiry},
        )

    async def bind_card_confirm(self, transaction_id: int, otp: str) -> dict[str, Any]:
        """POST /partner/bind-card/confirm — SMS bilan biriktirishni tasdiqlash."""
        return await self._post(
            "/partner/bind-card/confirm",
            {"transaction_id": transaction_id, "otp": otp},
        )

    async def list_cards(self, card_token: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if card_token:
            payload["card_token"] = card_token
        return await self._post("/partner/list-cards", payload)

    async def remove_card(self, card_token: str) -> dict[str, Any]:
        return await self._post("/partner/remove-card", {"card_token": card_token})

    # ===== Callback signature =====

    @staticmethod
    def verify_callback_signature(body: bytes, signature_header: str | None) -> bool:
        """Atmos webhook X-SIGNATURE header — HMAC-SHA256(callback_secret, body)."""
        secret = settings.ATMOS_CALLBACK_SECRET
        if not secret or not signature_header:
            return False
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected.lower(), signature_header.strip().lower())

    async def aclose(self) -> None:
        await self._client.aclose()


atmos = AtmosClient()
