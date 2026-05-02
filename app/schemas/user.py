from datetime import datetime

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


class TelegramAuthIn(BaseModel):
    """Telegram Login Widget'dan kelgan ma'lumotlar."""
    id: int
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    photo_url: str | None = None
    auth_date: int
    hash: str


class TelegramOtpStartOut(BaseModel):
    token: str
    bot_link: str
    expires_in: int


class TelegramOtpVerifyIn(BaseModel):
    token: str
    code: str


class TelegramOtpStatusOut(BaseModel):
    status: str


class UserOut(BaseModel):
    id: int
    email: str | None = None
    username: str | None = None
    full_name: str | None = None
    role: str
    is_active: bool
    telegram_id: int | None = None
    telegram_username: str | None = None
    photo_url: str | None = None
    phone: str | None = None
    pickup_point_id: int | None = None
    store_id: int | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


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


class TelegramInfo(BaseModel):
    bot_username: str
    enabled: bool
