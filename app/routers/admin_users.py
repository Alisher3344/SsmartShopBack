"""Super admin uchun foydalanuvchilarni boshqarish."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_superadmin
from app.core.security import hash_password
from app.db.database import get_db
from app.models.user import User
from app.schemas.user import UserOut
from app.services import user_service

router = APIRouter(prefix="/admin/users", tags=["admin-users"], dependencies=[Depends(require_superadmin)])


_PASSWORD_UPPER_RE = re.compile(r"[A-Z]")
_PASSWORD_DIGIT_RE = re.compile(r"\d")
_PASSWORD_LETTER_RE = re.compile(r"[A-Za-z]")


def _validate_password(pwd: str) -> str:
    if len(pwd) < 6 or len(pwd) > 128:
        raise ValueError("Parol uzunligi 6 dan 128 belgigacha bo'lishi kerak")
    if not _PASSWORD_LETTER_RE.search(pwd):
        raise ValueError("Parolda kamida bitta harf bo'lishi kerak")
    if not _PASSWORD_UPPER_RE.search(pwd):
        raise ValueError("Parolda kamida bitta katta harf bo'lishi kerak")
    if not _PASSWORD_DIGIT_RE.search(pwd):
        raise ValueError("Parolda kamida bitta raqam bo'lishi kerak")
    return pwd


class AdminUserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    password: str | None = Field(default=None, min_length=6, max_length=128)

    @field_validator("password")
    @classmethod
    def _pwd(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _validate_password(v)

    @field_validator("full_name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Ism Familiya kamida 2 belgi bo'lishi kerak")
        return v


@router.get("", response_model=list[UserOut])
async def list_shop_users(
    search: str | None = Query(None, max_length=255),
    db: AsyncSession = Depends(get_db),
):
    """Telefon raqami bilan ro'yxatdan o'tgan oddiy foydalanuvchilar.
    Search: ism/familiya yoki telefon raqami bo'yicha (LIKE)."""
    q = select(User).where(User.role == "user").order_by(User.id.desc())
    if search:
        s = search.strip()
        if s:
            # Telefon faqat raqamlar
            digits = "".join(ch for ch in s if ch.isdigit())
            filters = [User.full_name.ilike(f"%{s}%")]
            if digits:
                filters.append(User.phone.ilike(f"%{digits}%"))
            q = q.where(or_(*filters))
    res = await db.execute(q.limit(500))
    return list(res.scalars().all())


@router.get("/{user_id}", response_model=UserOut)
async def get_shop_user(user_id: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(User).where(User.id == user_id, User.role == "user"))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Foydalanuvchi topilmadi")
    return user


@router.put("/{user_id}", response_model=UserOut)
async def update_shop_user(
    user_id: int, data: AdminUserUpdate, db: AsyncSession = Depends(get_db)
):
    """Super admin foydalanuvchining ism va/yoki parolini o'zgartiradi."""
    res = await db.execute(select(User).where(User.id == user_id, User.role == "user"))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Foydalanuvchi topilmadi")

    if data.full_name is not None:
        user.full_name = data.full_name
    if data.password is not None:
        user.hashed_password = hash_password(data.password)

    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shop_user(user_id: int, db: AsyncSession = Depends(get_db)):
    """Super admin foydalanuvchini va uning barcha bog'liq ma'lumotlarini o'chiradi.
    FK CASCADE bilan: orders, reviews va h.k. avtomatik tozalanadi.
    Profil rasmi /uploads dan ham o'chiriladi."""
    res = await db.execute(select(User).where(User.id == user_id, User.role == "user"))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Foydalanuvchi topilmadi")

    # Profil rasmini diskdan ham olib tashlaymiz
    user_service._delete_uploaded_file(user.photo_url)

    await db.delete(user)
    await db.commit()
