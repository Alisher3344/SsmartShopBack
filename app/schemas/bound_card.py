from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


def _config():
    return ConfigDict(
        from_attributes=True,
        alias_generator=to_camel,
        populate_by_name=True,
    )


class BindCardInitIn(BaseModel):
    card_number: str = Field(min_length=16, max_length=19)
    expiry: str = Field(min_length=4, max_length=4)

    @field_validator("card_number")
    @classmethod
    def _digits_card(cls, v: str) -> str:
        v = v.replace(" ", "").replace("-", "")
        if not v.isdigit():
            raise ValueError("Karta raqami faqat raqamlardan iborat bo'lishi kerak")
        return v

    @field_validator("expiry")
    @classmethod
    def _digits_expiry(cls, v: str) -> str:
        if not v.isdigit() or len(v) != 4:
            raise ValueError("Expiry format: YYMM (4 raqam)")
        return v

    model_config = _config()


class BindCardInitOut(BaseModel):
    bound_card_id: int
    bind_transaction_id: int

    model_config = _config()


class BindCardConfirmIn(BaseModel):
    bound_card_id: int
    otp: str = Field(min_length=4, max_length=8)

    @field_validator("otp")
    @classmethod
    def _digits(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit():
            raise ValueError("OTP faqat raqamlardan iborat bo'lishi kerak")
        return v

    model_config = _config()


class BoundCardOut(BaseModel):
    id: int
    user_id: int
    pan_masked: str | None
    expiry: str | None
    card_holder: str | None
    status: str
    is_default: bool
    last_used_at: datetime | None
    created_at: datetime
    # card_token mijozga ko'rsatilmaydi (xavfsizlik)

    model_config = _config()
