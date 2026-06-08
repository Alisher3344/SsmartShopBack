from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import login_limiter
from app.core.deps import get_current_user
from app.core.security import create_access_token
from app.db.database import get_db
from app.models.user import User
from app.schemas.user import (
    ProfileUpdate,
    Token,
    UserCreate,
    UserLogin,
    UserOut,
)
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(data: UserCreate, db: AsyncSession = Depends(get_db)):
    if await user_service.get_user_by_email(db, data.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    user = await user_service.create_user(db, data)
    token = create_access_token(user.id)
    return Token(access_token=token, user=UserOut.model_validate(user))


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")


@router.post("/login", response_model=Token)
async def login(data: UserLogin, request: Request, db: AsyncSession = Depends(get_db)):
    ip = _client_ip(request)
    allowed, retry = login_limiter.check(ip, data.login)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Juda ko'p urinish. {retry // 60} daqiqadan so'ng qayta urinib ko'ring.",
        )
    user = await user_service.authenticate_user(db, data.login, data.password)
    if not user:
        attempts, retry = login_limiter.record_failure(ip, data.login)
        if retry > 0:
            raise HTTPException(
                status_code=429,
                detail=f"3 marta noto'g'ri kiritildi. {retry // 60} daqiqaga bloklandi.",
            )
        left = login_limiter.MAX_ATTEMPTS - attempts
        raise HTTPException(
            status_code=401,
            detail=f"Login yoki parol noto'g'ri. {left} ta urinish qoldi.",
        )
    login_limiter.reset(ip, data.login)
    token = create_access_token(user.id)
    return Token(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me/profile", response_model=UserOut)
async def update_my_profile(
    data: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Foydalanuvchi o'z profilini yangilaydi: ism, familiya, tug'ilgan kun, rasm.
    Yangi rasm yuborilsa, eski rasm fayli /uploads dan o'chiriladi."""
    return await user_service.update_profile(db, current_user, data)
