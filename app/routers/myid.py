"""MyID OAuth / QR inplace router.

Endpointlar (mounted at /api/auth/myid):
  GET  /start         — frontend foydalanuvchini MyID authorization URL'ga yo'naltiradi
  GET  /callback      — MyID muvaffaqiyatdan keyin code+state bilan qaytaradi
  GET  /fail          — MyID muvaffaqiyatsizlikda reason_code bilan qaytaradi
  POST /qr-callback   — QR inplace webhook (MyID backend'idan JSON: code+extra_info)
"""
from __future__ import annotations

import logging
import secrets
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.myid import MyIDError, myid_oauth
from app.core.security import (
    create_access_token,
    create_myid_state,
    decode_myid_state,
)
from app.db.database import get_db
from app.services.myid_service import find_or_create_user_from_myid

router = APIRouter(prefix="/auth/myid", tags=["myid"])
log = logging.getLogger(__name__)

NONCE_COOKIE = "myid_nonce"
NONCE_COOKIE_TTL = 600  # 10 daqiqa, state JWT bilan bir xil


_REASON_CODES = {
    "-1": "Foydalanuvchi shaxsiy ma'lumotlarga ruxsat bermadi",
    "2": "Pasport ma'lumotlari noto'g'ri kiritildi",
    "3": "Tiriklik tasdig'i o'tmadi",
    "4": "Yuz tanib bo'lmadi",
    "5": "GCP xizmati ishlamayapti",
    "6": "Foydalanuvchi vafot etgan",
    "11": "MyID xizmati so'rovni ishlay olmadi",
    "20": "Rasm sifati past",
    "21": "Yuz to'liq kadrga tushmadi",
    "28": "Yuz topilmadi",
    "34": "Hujjat muddati tugagan",
}


def _frontend_redirect(url: str, params: dict[str, Any]) -> RedirectResponse:
    """Frontend'ga query string bilan redirect (token URL fragment'da yo'q —
    backend cookie qo'yib yuborsa xavfsizroq, lekin hozircha query bilan)."""
    sep = "&" if "?" in url else "?"
    return RedirectResponse(
        url=f"{url}{sep}{urlencode(params)}", status_code=status.HTTP_302_FOUND
    )


@router.get("/start")
async def start(
    return_to: str | None = Query(
        default=None,
        description="Muvaffaqiyatdan keyin foydalanuvchi qaytadigan frontend sahifa",
    ),
):
    """MyID authorization sahifasiga yo'naltirish.

    Nonce'ni HttpOnly cookie'da saqlaymiz va state JWT'ga shifrlab joylaymiz.
    Callback'da ikkalasi bir xil bo'lishi kerak — bu CSRF dan himoya qiladi.
    """
    nonce = secrets.token_urlsafe(24)
    state = create_myid_state(nonce, return_to)

    try:
        auth_url = myid_oauth.build_auth_url(state)
    except MyIDError as e:
        log.error("MyID start: %s", e)
        raise HTTPException(500, "MyID integratsiyasi sozlanmagan")

    redirect = RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)
    redirect.set_cookie(
        key=NONCE_COOKIE,
        value=nonce,
        max_age=NONCE_COOKIE_TTL,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/auth/myid",
    )
    return redirect


@router.get("/callback")
async def callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    reason_code: str | None = Query(default=None),
    myid_nonce: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    """MyID muvaffaqiyatli javobi. CSRF tekshiriladi, code → access_token → user_info,
    keyin SsmartShop JWT chiqarilib frontend'ga redirect qilinadi.
    """
    if error or reason_code or not code:
        return await _fail_redirect(reason_code or error, state)

    payload = decode_myid_state(state or "")
    if not payload:
        log.warning("MyID callback: state yaroqsiz yoki muddati tugagan")
        return _frontend_redirect(
            settings.MYID_FRONTEND_FAIL_URL, {"reason": "invalid_state"}
        )
    if not myid_nonce or myid_nonce != payload.get("nonce"):
        log.warning("MyID callback: nonce mos kelmadi (CSRF?)")
        return _frontend_redirect(
            settings.MYID_FRONTEND_FAIL_URL, {"reason": "csrf"}
        )

    try:
        token_resp = await myid_oauth.exchange_code(code)
        access_token = token_resp.get("access_token")
        if not access_token:
            raise MyIDError(f"access_token javobida yo'q: {token_resp!r}")
        user_info = await myid_oauth.get_user_info(access_token)
    except MyIDError as e:
        log.exception("MyID callback: %s", e)
        return _frontend_redirect(
            settings.MYID_FRONTEND_FAIL_URL, {"reason": "myid_api"}
        )

    # DEBUG: prod javob shaklini tekshirish uchun (vaqtincha — last_name
    # masalasi hal qilingach olib tashlanadi)
    try:
        import json as _json
        log.warning(
            "MYID-CALLBACK-RAW: token_keys=%s user_info=%s",
            list(token_resp.keys()) if isinstance(token_resp, dict) else type(token_resp).__name__,
            _json.dumps(user_info, ensure_ascii=False)[:4000],
        )
    except Exception:
        log.exception("MyID raw log failed")

    # MyID returns user info — may be wrapped in `profile`/`user`/`data` key
    info = (
        user_info.get("profile")
        or user_info.get("user")
        or user_info.get("data")
        or user_info
    )
    user = await find_or_create_user_from_myid(
        db,
        info if isinstance(info, dict) else {},
        raw=user_info if isinstance(user_info, dict) else None,
    )
    app_token = create_access_token(user.id)

    return_to = payload.get("rt") or settings.MYID_FRONTEND_SUCCESS_URL
    redirect = _frontend_redirect(
        return_to, {"access_token": app_token, "user_id": user.id}
    )
    # Nonce cookie'sini o'chiramiz — bir martalik
    redirect.delete_cookie(NONCE_COOKIE, path="/auth/myid")
    return redirect


async def _fail_redirect(reason_code: str | None, state: str | None) -> RedirectResponse:
    """Failure callback'i — frontend fail sahifasiga yo'naltirish."""
    payload = decode_myid_state(state or "") or {}
    return_to = payload.get("rt") or settings.MYID_FRONTEND_FAIL_URL
    reason_text = _REASON_CODES.get(str(reason_code), "Identifikatsiya o'tmadi")
    return _frontend_redirect(
        return_to,
        {"reason_code": reason_code or "", "reason": reason_text},
    )


@router.get("/fail")
async def fail(
    state: str | None = Query(default=None),
    reason_code: str | None = Query(default=None),
):
    """MyID FailURL'da ro'yxatdan o'tkazilgan endpoint (alohida URL talab qilsa)."""
    return await _fail_redirect(reason_code, state)


class QRCallbackPayload(BaseModel):
    code: str
    extra_info: dict[str, Any] = {}


@router.post("/qr-callback")
async def qr_callback(
    payload: QRCallbackPayload, db: AsyncSession = Depends(get_db)
):
    """QR inplace webhook — MyID backend → bizning backend.

    Foydalanuvchi QR'ni skanerlab tasdiqlagandan keyin MyID server bizga JSON
    yuboradi (code + extra_info). Bu webhook foydalanuvchi browser'i emas, MyID
    server'idan keladi, shuning uchun state/nonce yo'q.
    `extra_info` QR'da yuborilgan kalit-qiymat juftliklarini qaytaradi
    (masalan, kiosk_id, operator) — kim QR'ni skanerlaganini aniqlaymiz.
    """
    try:
        token_resp = await myid_oauth.exchange_code(payload.code)
        access_token = token_resp.get("access_token")
        if not access_token:
            raise MyIDError(f"access_token yo'q: {token_resp!r}")
        user_info = await myid_oauth.get_user_info(access_token)
    except MyIDError as e:
        log.exception("MyID qr-callback: %s", e)
        raise HTTPException(502, "MyID javob bermadi")

    info = (
        user_info.get("profile")
        or user_info.get("user")
        or user_info.get("data")
        or user_info
    )
    user = await find_or_create_user_from_myid(
        db,
        info if isinstance(info, dict) else {},
        raw=user_info if isinstance(user_info, dict) else None,
    )

    return {
        "ok": True,
        "user_id": user.id,
        "extra_info": payload.extra_info,
    }
