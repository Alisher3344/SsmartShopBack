"""MyID OAuth klienti — Redirect va QR inplace metodlari.

Doc: https://docs.myid.uz/

Flow:
  1. build_auth_url(state) → frontend foydalanuvchini shu URL'ga yo'naltiradi
  2. MyID callback'da /api/auth/myid/callback'ga ?code=&state= qaytaradi
  3. exchange_code(code) → access_token + refresh_token
  4. get_user_info(access_token) → shaxsiy ma'lumotlar (FIO, PINFL, pasport, ...)

`client_secret` faqat shu yerda (backend'da) ishlatiladi.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)


class MyIDError(RuntimeError):
    """MyID API xatosi (tarmoq, auth, yoki noto'g'ri javob)."""


class MyIDBusinessError(MyIDError):
    """MyID biznes-mantiq xatosi (4xx/5xx, response da `error`/`message`)."""

    def __init__(self, code: Any, description: str | None = None):
        self.code = code
        self.description = description or ""
        super().__init__(f"MyID error {code}: {description}")


class MyIDOAuthClient:
    """`devmyid.uz` / `myid.uz` OAuth2 endpointlari uchun klient."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.MYID_OAUTH_BASE_URL,
            timeout=float(settings.MYID_OAUTH_TIMEOUT),
        )

    def build_auth_url(self, state: str, *, method: str | None = None) -> str:
        """Foydalanuvchini yo'naltirish uchun authorization URL yasash.

        MyID redirect_uri'ni MyID adminida ro'yxatdan o'tgan qiymat bilan
        bayt-baytda solishtiradi, shuning uchun `settings`'dagi qiymatni
        o'zgartirmasdan uzatamiz.
        """
        if not settings.MYID_OAUTH_CLIENT_ID:
            raise MyIDError("MYID_OAUTH_CLIENT_ID .env'da yo'q")
        if not settings.MYID_OAUTH_REDIRECT_URI:
            raise MyIDError("MYID_OAUTH_REDIRECT_URI .env'da yo'q")

        params = {
            "client_id": settings.MYID_OAUTH_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": settings.MYID_OAUTH_REDIRECT_URI,
            "scope": settings.MYID_OAUTH_SCOPE,
            "method": method or settings.MYID_OAUTH_METHOD,
            "state": state,
        }
        return f"{settings.MYID_OAUTH_BASE_URL.rstrip('/')}/api/v1/oauth2/authorization?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict[str, Any]:
        """`code` ni `access_token` ga almashtirish.

        Doc: POST /api/v1/oauth2/access-token (application/x-www-form-urlencoded)
        """
        if not settings.MYID_OAUTH_CLIENT_SECRET:
            raise MyIDError("MYID_OAUTH_CLIENT_SECRET .env'da yo'q")

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": settings.MYID_OAUTH_CLIENT_ID,
            "client_secret": settings.MYID_OAUTH_CLIENT_SECRET,
            "redirect_uri": settings.MYID_OAUTH_REDIRECT_URI,
        }
        try:
            r = await self._client.post(
                "/api/v1/oauth2/access-token",
                data=data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
            )
        except httpx.HTTPError as e:
            raise MyIDError(f"MyID access-token: tarmoq xatosi ({e})") from e
        return self._parse(r, "access-token")

    async def get_user_info(self, access_token: str) -> dict[str, Any]:
        """`/api/v1/users/me` orqali shaxsiy ma'lumotlar."""
        try:
            r = await self._client.get(
                "/api/v1/users/me",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
                timeout=30.0,
            )
        except httpx.HTTPError as e:
            raise MyIDError(f"MyID users/me: tarmoq xatosi ({e})") from e
        return self._parse(r, "users/me")

    async def refresh_token(self, refresh_token: str) -> dict[str, Any]:
        """`access_token` muddati tugaganda — refresh_token orqali yangilash."""
        try:
            r = await self._client.post(
                "/api/v1/oauth2/refresh-token",
                json={
                    "refresh_token": refresh_token,
                    "client_id": settings.MYID_OAUTH_CLIENT_ID,
                    "client_secret": settings.MYID_OAUTH_CLIENT_SECRET,
                },
                headers={"Accept": "application/json"},
            )
        except httpx.HTTPError as e:
            raise MyIDError(f"MyID refresh-token: tarmoq xatosi ({e})") from e
        return self._parse(r, "refresh-token")

    @staticmethod
    def _parse(r: httpx.Response, path: str) -> dict[str, Any]:
        try:
            data = r.json() if r.content else {}
        except ValueError:
            if 200 <= r.status_code < 300:
                return {}
            raise MyIDError(f"MyID {path} {r.status_code}: JSON parse ({r.text!r})")
        if not isinstance(data, dict):
            if 200 <= r.status_code < 300:
                return {"result": data}
            raise MyIDError(f"MyID {path} {r.status_code}: {data!r}")
        if 200 <= r.status_code < 300:
            # MyID muvaffaqiyatli javobida ham xatolik bo'lishi mumkin
            err = data.get("error") or data.get("code")
            if err and str(err).upper() not in ("OK", "0", "0000"):
                raise MyIDBusinessError(
                    err, data.get("error_description") or data.get("message")
                )
            return data
        code = data.get("error") or data.get("code") or r.status_code
        msg = (
            data.get("error_description")
            or data.get("message")
            or data.get("description")
            or r.text
        )
        raise MyIDBusinessError(code, msg)

    async def aclose(self) -> None:
        await self._client.aclose()


myid_oauth = MyIDOAuthClient()
