from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = None


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str | None = None
    password: str = Field(min_length=6, max_length=128)


class UserLogin(BaseModel):
    # login - username yoki email
    login: str
    password: str


class UserOut(BaseModel):
    id: int
    email: str | None = None
    username: str | None = None
    full_name: str | None = None
    role: str
    is_active: bool
    photo_url: str | None = None
    phone: str | None = None
    birth_date: date | None = None
    # Paymo instalment uchun KYC profil
    passport: str | None = None
    middlename: str | None = None
    address: str | None = None
    address_payer: str | None = None
    work_place: str | None = None
    pickup_point_id: int | None = None
    store_id: int | None = None
    created_at: datetime
    # MyID identifikatsiyasi (success sahifa shu maydonlarni ko'rsatadi)
    myid_passport_serial: str | None = None
    myid_verified_at: datetime | None = None
    myid_raw: dict[str, Any] | None = None

    model_config = ConfigDict(from_attributes=True)


class ProfileUpdate(BaseModel):
    """Foydalanuvchi o'z profili (ism, familiya, tug'ilgan kun, rasm, instalment KYC)."""
    first_name: str | None = Field(default=None, min_length=1, max_length=120)
    last_name: str | None = Field(default=None, min_length=1, max_length=120)
    birth_date: date | None = None
    photo_url: str | None = Field(default=None, max_length=512)
    # Paymo instalment uchun KYC (bir marta to'ldirilib qayta ishlatiladi)
    passport: str | None = Field(default=None, pattern=r"^\d{14}$")  # PINFL/JSHSHIR
    middlename: str | None = Field(default=None, min_length=1, max_length=120)
    address: str | None = Field(default=None, min_length=1, max_length=512)
    address_payer: str | None = Field(default=None, min_length=1, max_length=512)
    work_place: str | None = Field(default=None, min_length=1, max_length=255)


class SalesAdminCreate(BaseModel):
    """Sotuv admini — universal admin (mahsulot/banner ruxsati, magazinga bog'lanmaydi)."""
    full_name: str = Field(min_length=2, max_length=255)
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    phone: str | None = Field(default=None, max_length=32)
    store_id: int | None = None


class SalesAdminUpdate(BaseModel):
    full_name: str | None = None
    username: str | None = Field(default=None, min_length=2, max_length=64)
    password: str | None = Field(default=None, min_length=6, max_length=128)
    phone: str | None = None
    is_active: bool | None = None
    store_id: int | None = None


class StaffAdminCreate(BaseModel):
    """Magazin admini (staff) — magazinga majburiy biriktiriladi."""
    full_name: str = Field(min_length=2, max_length=255)
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    phone: str | None = Field(default=None, max_length=32)
    store_id: int


class StaffAdminUpdate(BaseModel):
    full_name: str | None = None
    username: str | None = Field(default=None, min_length=2, max_length=64)
    password: str | None = Field(default=None, min_length=6, max_length=128)
    phone: str | None = None
    is_active: bool | None = None
    store_id: int | None = None


class TvAdminCreate(BaseModel):
    """SsmartTV admin — TV backendida yaratiladi (server-to-server proxy).
    Maydon cheklovlari TV backendiga mos (username ≥3, parol ≥8)."""
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=120)
    role: Literal["admin", "staff"] = "admin"


class TvAdminUpdate(BaseModel):
    """SsmartTV admin tahrirlash — faqat berilgan maydonlar yuboriladi."""
    username: str | None = Field(default=None, min_length=3, max_length=64)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=120)
    role: Literal["admin", "staff"] | None = None


class PickupAdminCreate(BaseModel):
    """Punkt admini yaratish — ko'p admin bo'lishi mumkin."""
    full_name: str = Field(min_length=2, max_length=255)
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    phone: str = Field(min_length=4, max_length=32)


class PickupAdminUpdate(BaseModel):
    full_name: str | None = None
    username: str | None = Field(default=None, min_length=2, max_length=64)
    password: str | None = Field(default=None, min_length=6, max_length=128)
    phone: str | None = None
    is_active: bool | None = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
