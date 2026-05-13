from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(subject: str | int, expires_minutes: int | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": str(subject), "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None


REGISTRATION_TOKEN_TTL_MINUTES = 10
PASSWORD_RESET_TOKEN_TTL_MINUTES = 10


def _scoped_phone_token(phone: str, scope: str, ttl_minutes: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
    payload = {"phone": phone, "scope": scope, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def _decode_scoped_phone_token(token: str, expected_scope: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None
    if payload.get("scope") != expected_scope:
        return None
    phone = payload.get("phone")
    return phone if isinstance(phone, str) else None


def create_registration_token(phone: str) -> str:
    """OTP tasdiqlanganidan keyin ro'yxatdan o'tishni yakunlash uchun qisqa muddatli token."""
    return _scoped_phone_token(phone, "register", REGISTRATION_TOKEN_TTL_MINUTES)


def decode_registration_token(token: str) -> str | None:
    """Registration token'ni tekshiradi va phone'ni qaytaradi. Yaroqsiz bo'lsa None."""
    return _decode_scoped_phone_token(token, "register")


def create_password_reset_token(phone: str) -> str:
    """SMS OTP tasdiqlanganidan keyin parolni tiklash uchun qisqa muddatli token."""
    return _scoped_phone_token(phone, "password_reset", PASSWORD_RESET_TOKEN_TTL_MINUTES)


def decode_password_reset_token(token: str) -> str | None:
    return _decode_scoped_phone_token(token, "password_reset")
