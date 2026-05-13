"""SMS orqali OTP — ro'yxatdan o'tish flow'i (Eskiz)."""
from __future__ import annotations

import logging
import random
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import login_limiter
from app.core.config import settings
from app.core.eskiz import EskizError, eskiz
from app.core.security import (
    create_access_token,
    create_password_reset_token,
    create_registration_token,
    decode_password_reset_token,
    decode_registration_token,
    hash_password,
    verify_password,
)
from app.db.database import get_db
from app.models.sms_otp import SmsOtp
from app.models.user import User
from app.schemas.user import Token, UserOut

router = APIRouter(prefix="/users", tags=["users"])
log = logging.getLogger(__name__)

OTP_TTL_SECONDS = 300            # 5 daqiqa
RESEND_COOLDOWN_SECONDS = 60     # 60 sekund
MAX_ATTEMPTS = 5
CODE_LEN = 4

_PASSWORD_UPPER_RE = re.compile(r"[A-Z]")
_PASSWORD_DIGIT_RE = re.compile(r"\d")
_PASSWORD_LETTER_RE = re.compile(r"[A-Za-z]")


def _validate_password_strength(pwd: str) -> str:
    if len(pwd) < 6 or len(pwd) > 128:
        raise ValueError("Parol uzunligi 6 dan 128 belgigacha bo'lishi kerak")
    if not _PASSWORD_LETTER_RE.search(pwd):
        raise ValueError("Parolda kamida bitta harf bo'lishi kerak")
    if not _PASSWORD_UPPER_RE.search(pwd):
        raise ValueError("Parolda kamida bitta katta harf bo'lishi kerak")
    if not _PASSWORD_DIGIT_RE.search(pwd):
        raise ValueError("Parolda kamida bitta raqam bo'lishi kerak")
    return pwd


def _norm_phone(v: str) -> str:
    v = v.strip().lstrip("+")
    if not v.isdigit():
        raise ValueError("Faqat raqamlar")
    if not v.startswith("998") or len(v) != 12:
        raise ValueError("Telefon raqam +998 formatida bo'lishi kerak")
    return v


class _PhonePayload(BaseModel):
    phone: str = Field(..., min_length=12, max_length=15)

    @field_validator("phone")
    @classmethod
    def _norm(cls, v: str) -> str:
        return _norm_phone(v)


class RequestPayload(_PhonePayload):
    pass


class VerifyPayload(_PhonePayload):
    code: str = Field(..., min_length=4, max_length=4)

    @field_validator("code")
    @classmethod
    def _digits(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("Kod faqat raqamlardan iborat bo'lishi kerak")
        return v


class VerifyOut(BaseModel):
    registration_token: str
    expires_in: int = 600  # 10 minut


class CompleteRegisterPayload(BaseModel):
    registration_token: str = Field(..., min_length=10)
    password: str = Field(..., min_length=6, max_length=128)
    full_name: str = Field(..., min_length=2, max_length=255)

    @field_validator("password")
    @classmethod
    def _pwd(cls, v: str) -> str:
        return _validate_password_strength(v)

    @field_validator("full_name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Ism Familiya kamida 2 belgi bo'lishi kerak")
        return v


class PhoneLoginPayload(BaseModel):
    phone: str = Field(..., min_length=12, max_length=15)
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("phone")
    @classmethod
    def _norm(cls, v: str) -> str:
        return _norm_phone(v)


class ResetVerifyOut(BaseModel):
    reset_token: str
    expires_in: int = 600


class ResetCompletePayload(BaseModel):
    reset_token: str = Field(..., min_length=10)
    password: str = Field(..., min_length=6, max_length=128)

    @field_validator("password")
    @classmethod
    def _pwd(cls, v: str) -> str:
        return _validate_password_strength(v)


def _gen_code() -> str:
    return f"{random.randint(1000, 9999)}"


def _build_message(code: str) -> str:
    tpl = settings.SMS_OTP_TEMPLATE.replace("\\n", "\n")
    return tpl.format(code=code)


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")


async def _phone_already_registered(db: AsyncSession, phone: str) -> bool:
    """Foydalanuvchi shu phone bilan ro'yxatdan o'tgan va paroli bormi?"""
    user = (await db.execute(
        select(User).where(User.phone == phone, User.hashed_password.is_not(None))
    )).scalar_one_or_none()
    return user is not None


@router.post("/sms-otp/request", status_code=status.HTTP_204_NO_CONTENT)
async def request_otp(payload: RequestPayload, db: AsyncSession = Depends(get_db)):
    """Ro'yxatdan o'tish uchun SMS yuborish. Mavjud foydalanuvchi bo'lsa rad etadi."""
    phone = payload.phone

    if await _phone_already_registered(db, phone):
        raise HTTPException(409, "Bu raqamda allaqachon hisob mavjud. Hisobga kiring.")

    # Cooldown — oxirgi yuborilganidan beri RESEND_COOLDOWN_SECONDS o'tdimi?
    last = (await db.execute(
        select(SmsOtp).where(SmsOtp.phone == phone).order_by(SmsOtp.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    if last:
        elapsed = (datetime.now(timezone.utc) - last.created_at).total_seconds()
        if elapsed < RESEND_COOLDOWN_SECONDS:
            wait = int(RESEND_COOLDOWN_SECONDS - elapsed)
            raise HTTPException(429, f"Iltimos {wait} sekunddan keyin qayta urinib ko'ring")

    code = _gen_code()
    db.add(SmsOtp(
        phone=phone,
        code=code,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=OTP_TTL_SECONDS),
    ))
    await db.commit()

    try:
        await eskiz.send_sms(phone, _build_message(code))
    except EskizError as e:
        log.exception("Eskiz send failed for %s: %s", phone, e)
        raise HTTPException(502, "SMS yuborib bo'lmadi. Birozdan keyin urinib ko'ring.")
    return None


@router.post("/sms-otp/verify", response_model=VerifyOut)
async def verify_otp(payload: VerifyPayload, db: AsyncSession = Depends(get_db)):
    """OTP'ni tekshiradi. Foydalanuvchi YARATMAYDI — registration_token qaytaradi.
    Foydalanuvchi keyin /users/register/complete chaqirib parol va ism qo'shadi."""
    phone = payload.phone
    now = datetime.now(timezone.utc)

    if await _phone_already_registered(db, phone):
        raise HTTPException(409, "Bu raqamda allaqachon hisob mavjud. Hisobga kiring.")

    otp = (await db.execute(
        select(SmsOtp)
        .where(SmsOtp.phone == phone, SmsOtp.used == False)  # noqa: E712
        .order_by(SmsOtp.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    if not otp:
        raise HTTPException(400, "Kod topilmadi. Yangi kod so'rang.")
    if otp.expires_at < now:
        raise HTTPException(400, "Kod muddati tugagan. Yangi kod so'rang.")
    if otp.attempts >= MAX_ATTEMPTS:
        raise HTTPException(429, "Juda ko'p urinish. Yangi kod so'rang.")

    otp.attempts += 1
    if otp.code != payload.code:
        await db.commit()
        raise HTTPException(400, "Kod noto'g'ri")

    otp.used = True
    await db.execute(delete(SmsOtp).where(SmsOtp.phone == phone, SmsOtp.id != otp.id))
    await db.commit()

    reg_token = create_registration_token(phone)
    return VerifyOut(registration_token=reg_token, expires_in=600)


# ===== OTP tasdiqlash uchun umumiy yordamchi (reset flow'da qayta ishlatiladi) =====
async def _consume_otp(db: AsyncSession, phone: str, code: str) -> None:
    """Yangi OTP yozuvini topib tekshiradi va used=True qiladi. Xato bo'lsa HTTPException."""
    now = datetime.now(timezone.utc)
    otp = (await db.execute(
        select(SmsOtp)
        .where(SmsOtp.phone == phone, SmsOtp.used == False)  # noqa: E712
        .order_by(SmsOtp.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    if not otp:
        raise HTTPException(400, "Kod topilmadi. Yangi kod so'rang.")
    if otp.expires_at < now:
        raise HTTPException(400, "Kod muddati tugagan. Yangi kod so'rang.")
    if otp.attempts >= MAX_ATTEMPTS:
        raise HTTPException(429, "Juda ko'p urinish. Yangi kod so'rang.")

    otp.attempts += 1
    if otp.code != code:
        await db.commit()
        raise HTTPException(400, "Kod noto'g'ri")

    otp.used = True
    await db.execute(delete(SmsOtp).where(SmsOtp.phone == phone, SmsOtp.id != otp.id))
    await db.commit()


async def _send_otp_with_cooldown(db: AsyncSession, phone: str) -> None:
    """Cooldown tekshiradi, OTP yaratadi, SMS yuboradi."""
    last = (await db.execute(
        select(SmsOtp).where(SmsOtp.phone == phone).order_by(SmsOtp.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    if last:
        elapsed = (datetime.now(timezone.utc) - last.created_at).total_seconds()
        if elapsed < RESEND_COOLDOWN_SECONDS:
            wait = int(RESEND_COOLDOWN_SECONDS - elapsed)
            raise HTTPException(429, f"Iltimos {wait} sekunddan keyin qayta urinib ko'ring")

    code = _gen_code()
    db.add(SmsOtp(
        phone=phone,
        code=code,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=OTP_TTL_SECONDS),
    ))
    await db.commit()

    try:
        await eskiz.send_sms(phone, _build_message(code))
    except EskizError as e:
        log.exception("Eskiz send failed for %s: %s", phone, e)
        raise HTTPException(502, "SMS yuborib bo'lmadi. Birozdan keyin urinib ko'ring.")


@router.post("/register/complete", response_model=Token, status_code=status.HTTP_201_CREATED)
async def complete_registration(
    payload: CompleteRegisterPayload, db: AsyncSession = Depends(get_db)
):
    """Registration token + parol + ism orqali yangi foydalanuvchi yaratish."""
    phone = decode_registration_token(payload.registration_token)
    if not phone:
        raise HTTPException(400, "Ro'yxatdan o'tish sessiyasi yaroqsiz yoki muddati tugagan. Qaytadan boshlang.")

    # Race condition tekshiruvi — boshqa so'rov shu phone bilan user yaratgan bo'lishi mumkin
    if await _phone_already_registered(db, phone):
        raise HTTPException(409, "Bu telefon raqam allaqachon ro'yxatdan o'tgan.")

    # Mavjud phone-only user (telegram orqali kelganlar) bo'lsa — uni update qilamiz, dublikat yaratmaymiz
    existing = (await db.execute(
        select(User).where(User.phone == phone)
    )).scalar_one_or_none()

    if existing:
        existing.hashed_password = hash_password(payload.password)
        existing.full_name = payload.full_name
        if existing.role not in ("user", "admin", "superadmin", "staff", "pickup_admin"):
            existing.role = "user"
        existing.is_active = True
        user = existing
    else:
        user = User(
            phone=phone,
            hashed_password=hash_password(payload.password),
            full_name=payload.full_name,
            role="user",
            is_active=True,
        )
        db.add(user)
        await db.flush()

    await db.commit()
    await db.refresh(user)

    token = create_access_token(user.id)
    return Token(access_token=token, user=UserOut.model_validate(user))


@router.post("/phone-login", response_model=Token)
async def phone_login(
    payload: PhoneLoginPayload, request: Request, db: AsyncSession = Depends(get_db)
):
    """Telefon raqam + parol orqali hisobga kirish."""
    ip = _client_ip(request)
    allowed, retry = login_limiter.check(ip, payload.phone)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Juda ko'p urinish. {retry // 60} daqiqadan so'ng qayta urinib ko'ring.",
        )

    user = (await db.execute(
        select(User).where(User.phone == payload.phone, User.is_active == True)  # noqa: E712
    )).scalar_one_or_none()

    if not user or not user.hashed_password:
        # Hisob umuman yo'q yoki parolsiz (legacy). Bu axborot xatosi, brute-force
        # attempt emas — limiter'ga yozmaymiz, aks holda foydalanuvchi yangi raqamlarni
        # sinab ko'rib o'zini o'zi bloklab qo'yadi.
        raise HTTPException(
            status_code=404,
            detail="Bu raqamda hisob yaratilmagan. Ro'yxatdan o'ting.",
        )

    if not verify_password(payload.password, user.hashed_password):
        attempts, retry = login_limiter.record_failure(ip, payload.phone)
        if retry > 0:
            raise HTTPException(
                status_code=429,
                detail=f"3 marta noto'g'ri kiritildi. {retry // 60} daqiqaga bloklandi.",
            )
        left = login_limiter.MAX_ATTEMPTS - attempts
        raise HTTPException(
            status_code=401,
            detail=f"Parol noto'g'ri. {left} ta urinish qoldi.",
        )

    login_limiter.reset(ip, payload.phone)
    token = create_access_token(user.id)
    return Token(access_token=token, user=UserOut.model_validate(user))


# ============ Parolni tiklash flow'i ============

@router.post("/password-reset/request", status_code=status.HTTP_204_NO_CONTENT)
async def password_reset_request(payload: RequestPayload, db: AsyncSession = Depends(get_db)):
    """Parolni tiklash uchun SMS yuborish. Hisob yo'q bo'lsa 404."""
    phone = payload.phone
    user = (await db.execute(
        select(User).where(
            User.phone == phone,
            User.is_active == True,  # noqa: E712
            User.hashed_password.is_not(None),
        )
    )).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Bu raqamda hisob yaratilmagan. Ro'yxatdan o'ting.")
    await _send_otp_with_cooldown(db, phone)
    return None


@router.post("/password-reset/verify", response_model=ResetVerifyOut)
async def password_reset_verify(payload: VerifyPayload, db: AsyncSession = Depends(get_db)):
    """OTP tasdiqlash. Reset token qaytaradi (10 min TTL)."""
    phone = payload.phone
    # Hisob bor ekanligini qaytadan tekshiramiz (request va verify orasida o'chgan bo'lishi mumkin)
    user = (await db.execute(
        select(User).where(
            User.phone == phone,
            User.is_active == True,  # noqa: E712
            User.hashed_password.is_not(None),
        )
    )).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Bu raqamda hisob yaratilmagan.")

    await _consume_otp(db, phone, payload.code)
    reset_token = create_password_reset_token(phone)
    return ResetVerifyOut(reset_token=reset_token, expires_in=600)


@router.post("/password-reset/complete", response_model=Token)
async def password_reset_complete(
    payload: ResetCompletePayload, db: AsyncSession = Depends(get_db)
):
    """Yangi parolni saqlash va hisobga kirish."""
    phone = decode_password_reset_token(payload.reset_token)
    if not phone:
        raise HTTPException(400, "Tiklash sessiyasi yaroqsiz yoki muddati tugagan. Qaytadan boshlang.")

    user = (await db.execute(
        select(User).where(User.phone == phone, User.is_active == True)  # noqa: E712
    )).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Foydalanuvchi topilmadi.")

    user.hashed_password = hash_password(payload.password)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(user.id)
    return Token(access_token=token, user=UserOut.model_validate(user))
