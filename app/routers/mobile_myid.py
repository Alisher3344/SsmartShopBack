"""MyID Mobile SDK (new flow) endpoint'lari — Flutter APK uchun.

Mounted at `/api/mobile/auth/myid/*` (mobile_app sub-app ichida).

New flow oqimi:
  1. Flutter → POST /api/mobile/auth/myid/session  (Bearer kerak)
       Backend MyID server'da session yaratadi, `session_id` qaytaradi.
       Foydalanuvchining mavjud `passport` (PINFL), `phone`, `birth_date`
       ma'lumotlari avtomatik MyID'ga uzatiladi → SDK'da pasport kiritish
       ekran o'tkazib yuboriladi.

  2. Flutter SDK.initialize(session_id) — yuz skan, liveness → `code` qaytaradi

  3. Flutter → POST /api/mobile/auth/myid/verify  (Bearer kerak)
       Body: {code}
       Backend MyID'dan to'liq profil oladi, current_user'ga bog'laydi,
       reuid va comparison_value'ni saqlaydi. Yangilangan UserOut qaytaradi.

Arxitektur eslatma: MyID birinchi ro'yxatdan o'tishda emas, balki mavjud
shop foydalanuvchisi kredit/limit uchun shaxsini tasdiqlamoqchi bo'lganda
ishlatiladi. Shuning uchun ikkala endpoint ham auth talab qiladi.
"""
from __future__ import annotations

import logging
from datetime import date as date_cls

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.myid import MyIDBusinessError, MyIDError
from app.core.myid_sdk import myid_sdk
from app.db.database import get_db
from app.models.user import User
from app.schemas.user import UserOut
from app.services.myid_service import find_or_create_user_from_myid

log = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/myid", tags=["mobile"])


def _normalize_phone(raw: str | None) -> str | None:
    """`+998 (93) 428-56-36` → `998934285636`. MyID 998 prefiksli kutadi."""
    if not raw:
        return None
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    if digits.startswith("998") and len(digits) == 12:
        return digits
    if len(digits) == 9:
        return "998" + digits
    return None


def _iso_date(d: date_cls | None) -> str | None:
    return d.isoformat() if d else None


class MobileMyIDSessionRequest(BaseModel):
    """Optional override'lar — agar Flutter user profiliga ishonmasa.

    Bo'sh yuborilsa backend current_user ma'lumotlaridan to'ldiradi.
    """
    pinfl: str | None = Field(default=None, pattern=r"^\d{14}$", description="14 raqamli JSHSHIR")
    pass_data: str | None = Field(default=None, max_length=16, description="Pasport seriya+raqam")
    phone_number: str | None = Field(default=None, max_length=32)
    birth_date: date_cls | None = Field(default=None, description="ISO YYYY-MM-DD")
    is_resident: bool | None = None
    threshold: float | None = Field(default=None, ge=0.5, le=0.99)


class MobileMyIDSessionResponse(BaseModel):
    session_id: str


class MobileMyIDVerifyRequest(BaseModel):
    code: str = Field(..., min_length=1, description="MyID SDK qaytargan authorization code")


@router.post(
    "/session",
    response_model=MobileMyIDSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="MyID SDK uchun session yaratish",
    description=(
        "MyID server'da session yaratadi va `session_id` qaytaradi. Flutter "
        "shu `session_id`'ni SDK.initialize'ga uzatadi. Foydalanuvchining "
        "mavjud profili (`passport`/PINFL, `phone`, `birth_date`) avtomatik "
        "MyID'ga jo'natiladi — SDK pasport kiritish ekranini o'tkazib "
        "yuboradi. Auth talab qilinadi."
    ),
)
async def mobile_myid_session(
    payload: MobileMyIDSessionRequest,
    user: User = Depends(get_current_user),
) -> MobileMyIDSessionResponse:
    pinfl = payload.pinfl or user.passport
    pass_data = payload.pass_data or user.myid_passport_serial
    phone_number = _normalize_phone(payload.phone_number or user.phone)
    birth_date = _iso_date(payload.birth_date or user.birth_date)

    try:
        resp = await myid_sdk.create_session(
            pinfl=pinfl,
            pass_data=pass_data if not pinfl else None,
            phone_number=phone_number,
            birth_date=birth_date,
            is_resident=payload.is_resident,
            threshold=payload.threshold,
        )
    except MyIDBusinessError as e:
        log.warning("MyID session yaratish: %s", e)
        raise HTTPException(status_code=400, detail=str(e.description or e.code))
    except MyIDError as e:
        log.exception("MyID session yaratish (transport): %s", e)
        raise HTTPException(status_code=502, detail="MyID javob bermadi")

    session_id = resp.get("session_id")
    if not session_id:
        log.error("MyID session javobida session_id yo'q: %r", resp)
        raise HTTPException(status_code=502, detail="MyID session_id qaytarmadi")
    return MobileMyIDSessionResponse(session_id=str(session_id))


@router.post(
    "/verify",
    response_model=UserOut,
    status_code=status.HTTP_200_OK,
    summary="MyID SDK code'ni tasdiqlash va profilga biriktirish",
    description=(
        "Flutter MyID SDK qaytargan `code` ni MyID'da foydalanuvchi "
        "ma'lumotlariga almashtiradi va current_user'ga bog'laydi. "
        "`reuid` va `comparison_value` keyingi galga uchun saqlanadi. "
        "Auth talab qilinadi — natija current_user'ga yoziladi."
    ),
)
async def mobile_myid_verify(
    payload: MobileMyIDVerifyRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserOut:
    try:
        sdk_data = await myid_sdk.get_sdk_data(payload.code)
    except MyIDBusinessError as e:
        log.warning("MyID SDK data: %s", e)
        raise HTTPException(status_code=400, detail=str(e.description or e.code))
    except MyIDError as e:
        log.exception("MyID SDK data (transport): %s", e)
        raise HTTPException(status_code=502, detail="MyID javob bermadi")

    data = sdk_data.get("data") if isinstance(sdk_data.get("data"), dict) else {}
    profile = data.get("profile") if isinstance(data.get("profile"), dict) else None
    if not profile:
        log.error("MyID /sdk/data javobida profile yo'q: %r", sdk_data)
        raise HTTPException(status_code=502, detail="MyID profil ma'lumotlari yo'q")

    # find_or_create_user_from_myid current user'ni phone yoki pinfl orqali
    # topadi va yangilaydi. Logged-in foydalanuvchi pinfl/phone bilan bog'liq
    # bo'lgani uchun aynan shu user qaytadi.
    updated_user = await find_or_create_user_from_myid(db, profile, raw=sdk_data)

    # Logged-in user va MyID dan kelgan user mos kelmasa — bu xavfli holat.
    # Boshqa odamning MyID ma'lumotlari joriy hisobga bog'lanmasligi kerak.
    if updated_user.id != user.id:
        log.error(
            "MyID identifier xavfsizlik konflikti: current_user.id=%s, MyID match user.id=%s",
            user.id,
            updated_user.id,
        )
        raise HTTPException(
            status_code=409,
            detail=(
                "MyID ma'lumotlari boshqa foydalanuvchiga tegishli. "
                "Iltimos, mavjud hisob bilan kiring."
            ),
        )

    return UserOut.model_validate(updated_user)
