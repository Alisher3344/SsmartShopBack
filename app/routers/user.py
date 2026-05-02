from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, decode_access_token
from app.core.telegram_bot import get_bot_link
from app.db.database import get_db
from app.models.user import User
from app.schemas.user import (
    TelegramAuthIn,
    TelegramInfo,
    TelegramOtpStartOut,
    TelegramOtpStatusOut,
    TelegramOtpVerifyIn,
    Token,
    UserCreate,
    UserLogin,
    UserOut,
)
from app.services import auth_session_service, user_service

router = APIRouter(prefix="/users", tags=["users"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/users/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = await user_service.get_user_by_id(db, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(data: UserCreate, db: AsyncSession = Depends(get_db)):
    if await user_service.get_user_by_email(db, data.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    user = await user_service.create_user(db, data)
    token = create_access_token(user.id)
    return Token(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=Token)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    user = await user_service.authenticate_user(db, data.login, data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Login yoki parol noto'g'ri")
    token = create_access_token(user.id)
    return Token(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/telegram-info", response_model=TelegramInfo)
async def telegram_info():
    """Frontend Telegram Widget render qilish uchun bot username olishi."""
    return TelegramInfo(
        bot_username=settings.TELEGRAM_BOT_USERNAME or "",
        enabled=bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_BOT_USERNAME),
    )


@router.post("/telegram-auth", response_model=Token)
async def telegram_auth(data: TelegramAuthIn, db: AsyncSession = Depends(get_db)):
    if not settings.TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=503, detail="Telegram login disabled")
    if not user_service.verify_telegram_auth(data, settings.TELEGRAM_BOT_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid Telegram authentication")
    user = await user_service.get_or_create_telegram_user(db, data)
    token = create_access_token(user.id)
    return Token(access_token=token, user=UserOut.model_validate(user))


# ===== Telegram OTP login (bot orqali) =====

@router.post("/telegram-otp/start", response_model=TelegramOtpStartOut)
async def telegram_otp_start(db: AsyncSession = Depends(get_db)):
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_BOT_USERNAME:
        raise HTTPException(status_code=503, detail="Telegram bot disabled")
    session = await auth_session_service.create_session(db)
    return TelegramOtpStartOut(
        token=session.token,
        bot_link=get_bot_link(session.token),
        expires_in=auth_session_service.SESSION_TTL_SECONDS,
    )


@router.get("/telegram-otp/status", response_model=TelegramOtpStatusOut)
async def telegram_otp_status(token: str, db: AsyncSession = Depends(get_db)):
    session = await auth_session_service.get_by_token(db, token)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not auth_session_service.is_valid(session) and session.status != "verified":
        return TelegramOtpStatusOut(status="expired")
    return TelegramOtpStatusOut(status=session.status)


@router.post("/telegram-otp/verify", response_model=Token)
async def telegram_otp_verify(data: TelegramOtpVerifyIn, db: AsyncSession = Depends(get_db)):
    session = await auth_session_service.get_by_token(db, data.token)
    if not session or not auth_session_service.is_valid(session):
        raise HTTPException(status_code=400, detail="Sessiya topilmadi yoki muddati tugagan")
    if session.status != "code_sent" or not session.code:
        raise HTTPException(status_code=400, detail="Bot orqali kod hali yuborilmagan")
    if data.code.strip() != session.code:
        raise HTTPException(status_code=401, detail="Kod noto'g'ri")
    if not session.phone:
        raise HTTPException(status_code=400, detail="Telefon raqam topilmadi")

    user = await user_service.get_or_create_phone_user(
        db,
        phone=session.phone,
        telegram_id=session.telegram_id,
        telegram_username=session.telegram_username,
        full_name=session.full_name,
    )
    await auth_session_service.mark_verified(db, session)
    jwt = create_access_token(user.id)
    return Token(access_token=jwt, user=UserOut.model_validate(user))
