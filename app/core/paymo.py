"""Paymo / Atmos Partner API klienti.

Hostlar:
  - Auth:  https://partner.atmos.uz/token        (OAuth2 client credentials)
  - Data:  https://api.paymo.uz                  (scoring + instalment + transactions)

Auth oqimi (WSO2 API Manager standart):
  POST /token
  Authorization: Basic base64(consumer_key:consumer_secret)
  Content-Type: application/x-www-form-urlencoded
  body: grant_type=client_credentials
  -> {access_token, token_type: "Bearer", expires_in: 3600}

Token instance-da cache qilinadi:
  - expires_in - 60s xavfsizlik margin
  - 401 javob kelganda darhol relogin + bir marta retry
"""
from __future__ import annotations

import base64
import logging
import time
from typing import Any

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)


class PaymoError(RuntimeError):
    """Paymo API ishlamadi (tarmoq, auth, noto'g'ri javob)."""


class PaymoBusinessError(PaymoError):
    """Paymo biznes-mantiq xatosi (result.code != 'OK' yoki 4xx)."""

    def __init__(self, code: Any, description: str | None = None):
        self.code = code
        self.description = description or ""
        super().__init__(f"Paymo error {code}: {description}")


class PaymoClient:
    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expires_at: float = 0.0  # unix timestamp
        self._client = httpx.AsyncClient(
            base_url=settings.PAYMO_BASE_URL or "https://api.paymo.uz",
            timeout=float(settings.PAYMO_TIMEOUT or 20),
        )
        self._auth_client = httpx.AsyncClient(
            base_url=settings.PAYMO_AUTH_BASE_URL or "https://partner.atmos.uz",
            timeout=float(settings.PAYMO_TIMEOUT or 20),
        )

    async def _login(self) -> str:
        ck = settings.PAYMO_CONSUMER_KEY
        cs = settings.PAYMO_CONSUMER_SECRET
        if not ck or not cs:
            raise PaymoError(
                "PAYMO_CONSUMER_KEY/PAYMO_CONSUMER_SECRET .env'da yo'q"
            )
        basic = base64.b64encode(f"{ck}:{cs}".encode()).decode()
        try:
            r = await self._auth_client.post(
                "/token",
                headers={
                    "Authorization": f"Basic {basic}",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                data={"grant_type": "client_credentials"},
            )
        except httpx.HTTPError as e:
            raise PaymoError(f"Paymo /token: tarmoq xatosi ({e})") from e
        if r.status_code != 200:
            raise PaymoError(f"Paymo /token {r.status_code}: {r.text}")
        try:
            data = r.json() or {}
        except ValueError:
            raise PaymoError(f"Paymo /token: JSON parse xatosi ({r.text!r})")
        token = data.get("access_token") or data.get("token")
        if not token:
            raise PaymoError(f"Paymo /token: access_token javobida topilmadi ({data!r})")
        expires_in = int(data.get("expires_in") or 3600)
        # 60 sekund margin — TTL tugashidan oldin relogin qilamiz
        self._token = token
        self._token_expires_at = time.time() + max(0, expires_in - 60)
        return token

    async def _ensure_token(self) -> str:
        if self._token and time.time() < self._token_expires_at:
            return self._token
        return await self._login()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """401 da bitta retry bilan API so'rovi."""
        last_response: httpx.Response | None = None
        for attempt in (1, 2):
            token = await self._ensure_token()
            try:
                r = await self._client.request(
                    method,
                    path,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json",
                    },
                    json=json,
                    params=params,
                )
            except httpx.HTTPError as e:
                raise PaymoError(f"Paymo {method} {path}: tarmoq xatosi ({e})") from e
            if r.status_code == 401 and attempt == 1:
                self._token = None
                self._token_expires_at = 0.0
                continue
            last_response = r
            break
        assert last_response is not None
        return self._parse_response(method, path, last_response)

    @staticmethod
    def _parse_response(
        method: str, path: str, r: httpx.Response
    ) -> dict[str, Any]:
        # 204/empty (masalan DELETE)
        if r.status_code == 204 or not r.content:
            return {}
        try:
            data = r.json()
        except ValueError:
            if 200 <= r.status_code < 300:
                return {}
            raise PaymoError(f"Paymo {method} {path} {r.status_code}: {r.text!r}")
        if not isinstance(data, dict):
            if 200 <= r.status_code < 300:
                return {"result": data}
            raise PaymoError(f"Paymo {method} {path} {r.status_code}: {data!r}")
        # Atmos style: {"result": {"code": "OK"|"INSTALMENT_ERR_...", "description": "..."}}
        result = data.get("result") if isinstance(data.get("result"), dict) else None
        if 200 <= r.status_code < 300:
            if result is not None:
                code = result.get("code")
                if code is not None and str(code).upper() not in ("OK", "0"):
                    raise PaymoBusinessError(code, result.get("description"))
            else:
                code = data.get("code")
                if code is not None and str(code).upper() not in ("OK", "0"):
                    raise PaymoBusinessError(code, data.get("description"))
            return data
        # 4xx/5xx
        if result is not None:
            raise PaymoBusinessError(
                result.get("code") or r.status_code,
                result.get("description") or r.text,
            )
        raise PaymoBusinessError(
            data.get("code") or r.status_code,
            data.get("description") or data.get("message") or r.text,
        )

    # ===== Public API =====

    async def get_monthly_scoring(
        self,
        card_number: str,
        card_expiry: str,
        amount: int,
        percent: int,
    ) -> dict[str, Any]:
        """POST /scoring/get-monthly — kredit baholash uchun oylik holat."""
        return await self._request(
            "POST",
            "/scoring/get-monthly",
            json={
                "card_number": card_number,
                "card_expiry": card_expiry,
                "amount": str(amount),
                "percent": str(percent),
            },
        )

    async def create_instalment(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST /instalment/cmn — yangi rassrochka yaratish."""
        return await self._request("POST", "/instalment/cmn", json=payload)

    async def get_instalment(
        self, store_id: int, instalment_id: int | str
    ) -> dict[str, Any]:
        """GET /instalment/cmn/{store_id}/{instalment_id} — status + contract file."""
        return await self._request(
            "GET", f"/instalment/cmn/{store_id}/{instalment_id}"
        )

    async def cancel_instalment(
        self, store_id: int, instalment_id: int | str
    ) -> dict[str, Any]:
        """DELETE /instalment/cmn/{store_id}/{instalment_id} — annulyatsiya."""
        return await self._request(
            "DELETE", f"/instalment/cmn/{store_id}/{instalment_id}"
        )

    async def get_transactions(
        self,
        store_id: int,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
        page: int | None = None,
        size: int | None = None,
        loan_id: int | None = None,
        payment_id: int | None = None,
    ) -> dict[str, Any]:
        """GET /instalment/cmn/get-transactions — store bo'yicha to'lovlar.

        Filter param'lari: date_from, date_to (YYYY-MM-DD), page, size, loan_id,
        payment_id. Javob: {result, payments[], totalPayments, totalPages, currentPage}.
        """
        params: dict[str, Any] = {"store_id": store_id}
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        if page is not None:
            params["page"] = page
        if size is not None:
            params["size"] = size
        if loan_id is not None:
            params["loan_id"] = loan_id
        if payment_id is not None:
            params["payment_id"] = payment_id
        return await self._request(
            "GET", "/instalment/cmn/get-transactions", params=params
        )

    async def aclose(self) -> None:
        await self._client.aclose()
        await self._auth_client.aclose()


paymo = PaymoClient()
