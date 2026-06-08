from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class StoreBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    address: str | None = None
    phone: str | None = None
    description: str | None = None
    active: bool = True
    # Paymo'da ro'yxatdan o'tgan store ID (rassrochka yaratish uchun).
    # NULL bo'lsa bu magazin orqali instalment yaratib bo'lmaydi.
    paymo_store_id: int | None = None


class StoreCreate(StoreBase):
    pass


class StoreUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    address: str | None = None
    phone: str | None = None
    description: str | None = None
    active: bool | None = None
    paymo_store_id: int | None = None


class StoreOut(BaseModel):
    id: int
    name: str
    address: str | None
    phone: str | None
    description: str | None
    active: bool
    is_main: bool = False
    paymo_store_id: int | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
