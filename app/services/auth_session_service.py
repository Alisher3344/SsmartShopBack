import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth_session import AuthSession

SESSION_TTL_SECONDS = 600  # 10 daqiqa


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _generate_token(length: int = 24) -> str:
    return secrets.token_urlsafe(length)[:length]


def _generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


async def create_session(db: AsyncSession) -> AuthSession:
    session = AuthSession(
        token=_generate_token(),
        status="pending",
        expires_at=_now() + timedelta(seconds=SESSION_TTL_SECONDS),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def get_by_token(db: AsyncSession, token: str) -> AuthSession | None:
    result = await db.execute(select(AuthSession).where(AuthSession.token == token))
    return result.scalar_one_or_none()


async def attach_telegram_user(
    db: AsyncSession,
    session: AuthSession,
    telegram_id: int,
    telegram_username: str | None,
    full_name: str | None,
    phone: str,
) -> AuthSession:
    """Bot foydalanuvchi telefonini olganida — code generatsiya qilamiz."""
    session.telegram_id = telegram_id
    session.telegram_username = telegram_username
    session.full_name = full_name
    session.phone = phone
    session.code = _generate_code()
    session.status = "code_sent"
    await db.commit()
    await db.refresh(session)
    return session


async def mark_verified(db: AsyncSession, session: AuthSession) -> None:
    session.status = "verified"
    await db.commit()


def is_valid(session: AuthSession) -> bool:
    expires = session.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return _now() < expires


async def cleanup_expired(db: AsyncSession) -> None:
    now = _now()
    await db.execute(
        update(AuthSession)
        .where(AuthSession.status != "verified", AuthSession.expires_at < now)
        .values(status="expired")
    )
    await db.commit()
