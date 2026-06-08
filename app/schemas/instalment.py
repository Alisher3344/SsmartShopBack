"""Paymo instalment (rassrochka) schema'lari."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


def _config():
    return ConfigDict(
        from_attributes=True,
        alias_generator=to_camel,
        populate_by_name=True,
    )


class InstalmentCreateIn(BaseModel):
    """Mijoz tomonidan rassrochka yaratish so'rovi.

    KYC ma'lumotlari (passport, middlename, address, address_payer, work_place)
    User profilidan tortib olinadi. Bu yerda ishlatilmaydi.
    """

    order_id: int
    card_number: str = Field(..., min_length=16, max_length=19)
    card_expiry: str = Field(..., pattern=r"^\d{4}$", description="YYMM, masalan: 2509")
    total_amount: int = Field(..., gt=0, description="Umumiy summa (tiyin)")
    initial_amount: int = Field(..., ge=0, description="Boshlang'ich to'lov (tiyin)")
    period: int = Field(..., ge=1, le=36, description="Rassrochka muddati (oy)")
    start_month: str = Field(..., pattern=r"^\d{4}$", description="YYMM")
    pay_day: int = Field(..., ge=1, le=28, description="Oylik to'lov sanasi (1-28)")
    details: str | None = Field(default=None, max_length=512)
    contract: str | None = Field(default=None, max_length=512)
    debit_initial_amount: bool = Field(
        default=True, description="Boshlang'ich to'lovni kartadan yechishmi"
    )
    additional_number: str | None = Field(default=None, max_length=32)
    responsible_manager: str | None = Field(default=None, max_length=255)

    model_config = _config()


class InstalmentOut(BaseModel):
    id: int
    order_id: int
    user_id: int
    store_id: int | None
    paymo_instalment_id: str | None
    paymo_store_id: int | None
    status: str
    card_last4: str | None
    card_expiry: str | None
    total_amount: int
    initial_amount: int
    period: int
    start_month: str | None
    pay_day: int | None
    holder_name: str | None
    bank: str | None
    phone_number: str | None
    contract_file_url: str | None
    balance: int | None
    offer: str | None
    status_synced_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = _config()


class InstalmentStatusOut(BaseModel):
    """Polling endpoint javobi (yengilroq forma)."""

    id: int
    paymo_instalment_id: str | None
    status: str
    contract_file_url: str | None
    balance: int | None
    status_synced_at: datetime | None

    model_config = _config()


# ===== get-transactions (admin moliyaviy hisobot) =====

# Paymo paymentType enum (admin UI'da insoniy ko'rsatish uchun):
PAYMENT_TYPE_LABELS = {
    0: "PAYMO",
    1: "Direct",
    2: "Auto",
    3: "Billing/1C",
    4: "PINFL",
    5: "Terminal",
    6: "Cash",
    7: "Click",
    8: "PayMe",
    9: "P2P",
}


class TransactionItem(BaseModel):
    """Bitta to'lov yozuvi (Paymo /cmn/get-transactions).

    Atmos real javobi snake_case + `totalAmount` qaytaradi, shuning uchun
    alias'lar shunga moslangan (`amount` <- `totalAmount`).
    """

    loan_id: int
    payment_id: int
    amount: int = Field(alias="totalAmount")  # tiyin
    pay_time: str
    payment_type: int
    parent_id: int | None = None
    contract_id: str | None = None
    payment_type_label: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class TransactionsOut(BaseModel):
    """get-transactions javobi."""

    payments: list[TransactionItem]
    total_payments: int | None = Field(default=None, alias="totalPayments")
    total_pages: int | None = Field(default=None, alias="totalPages")
    current_page: int | None = Field(default=None, alias="currentPage")

    model_config = ConfigDict(populate_by_name=True)
