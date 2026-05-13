from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


def _config():
    return ConfigDict(
        from_attributes=True,
        alias_generator=to_camel,
        populate_by_name=True,
    )


class PaymentInitIn(BaseModel):
    """To'lov sessiyasini boshlash — buyurtma id'si yetarli."""

    order_id: int

    model_config = _config()


class PaymentInitOut(BaseModel):
    payment_id: int
    atmos_transaction_id: int
    amount_tiyin: int
    status: str

    model_config = _config()


class PaymentPreApplyIn(BaseModel):
    payment_id: int
    card_number: str = Field(min_length=16, max_length=19)
    # YYMM (e.g. '2801' = yanvar 2028) yoki MMYY — frontend qaysi formatda yuborsa shu
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


class PaymentPreApplyTokenIn(BaseModel):
    """Biriktirilgan karta orqali pre-apply."""

    payment_id: int
    card_token: str

    model_config = _config()


class PaymentPreApplyOut(BaseModel):
    payment_id: int
    status: str  # pending_otp

    model_config = _config()


class PaymentApplyIn(BaseModel):
    payment_id: int
    otp: str = Field(min_length=4, max_length=8)

    @field_validator("otp")
    @classmethod
    def _digits(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit():
            raise ValueError("OTP faqat raqamlardan iborat bo'lishi kerak")
        return v

    model_config = _config()


class PaymentOut(BaseModel):
    id: int
    order_id: int
    user_id: int | None
    atmos_transaction_id: int | None
    atmos_success_trans_id: int | None
    account: str
    amount_tiyin: int
    refunded_tiyin: int = 0
    status: str
    atmos_status_code: str | None
    atmos_status_message: str | None
    card_id: str | None
    ofd_url: str | None
    ofd_url_commission: str | None
    created_at: datetime
    updated_at: datetime

    model_config = _config()


class RefundIn(BaseModel):
    """Admin: to'lovni qaytarish. amount_tiyin yuborilsa partial, bo'lmasa full."""

    amount_tiyin: int | None = Field(default=None, ge=1)
    reason: str | None = Field(default=None, max_length=500)

    model_config = _config()


class RefundOut(BaseModel):
    payment_id: int
    refunded_tiyin: int
    payment_status: str  # confirmed | partially_refunded | refunded
    reverse_id: int | None = None  # partial bo'lsa Atmos qaytaradi
    atmos_status_code: str | None = None
    atmos_status_message: str | None = None

    model_config = _config()


class AtmosCallbackPayload(BaseModel):
    """Atmos webhook — har bir maydon Atmos tomonidan kelishi mumkin (ixtiyoriy)."""

    transaction_id: int | None = None
    success_trans_id: int | None = None
    store_id: int | str | None = None
    terminal_id: str | None = None
    account: str | None = None
    amount: int | None = None
    confirmed: bool | None = None
    status_code: str | None = None
    status_message: str | None = None
    card_id: str | None = None
    commission_value: str | int | None = None

    model_config = ConfigDict(extra="allow")  # Atmos qo'shimcha maydon yuborsa ham qabul
