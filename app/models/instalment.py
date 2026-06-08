"""Paymo orqali yaratilgan rassrochka (instalment) yozuvi.

Order bilan 1:1 bog'lanadi (bir buyurtmaga bir aktiv instalment).
Lifecycle: NOT_CONFIRMED -> CONFIRMED/ACTIVE -> CLOSED (yoki CANCELLED/FAILED).
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Instalment(Base):
    __tablename__ = "instalments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Bir order = bir instalment (unique constraint).
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    store_id: Mapped[int | None] = mapped_column(
        ForeignKey("stores.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Paymo'dan kelgan instalment ID (create dan keyin to'ladi).
    paymo_instalment_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, nullable=True
    )
    # Snapshot of stores.paymo_store_id at create time — agar keyin o'zgarsa ham
    # GET/DELETE chaqiruvlarida o'sha vaqtdagi qiymat ishlatiladi.
    paymo_store_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # NOT_CONFIRMED | CONFIRMED | ACTIVE | CLOSED | CANCELLED | FAILED
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="NOT_CONFIRMED", index=True
    )
    # Karta PII: faqat last4 va expiry niqobi (to'liq PAN hech qachon saqlanmaydi)
    card_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    card_expiry: Mapped[str | None] = mapped_column(String(5), nullable=True)  # MM/YY
    # Pul ko'rsatkichlari (tiyin)
    total_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    initial_amount: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    period: Mapped[int] = mapped_column(Integer, nullable=False)  # oylar
    start_month: Mapped[str | None] = mapped_column(String(4), nullable=True)  # YYMM
    pay_day: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1..31
    # Paymo javobidan keladigan ma'lumotlar
    holder_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bank: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    contract_file_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    balance: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    offer: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Audit / debug uchun raw javoblar (card_number redacted!)
    raw_create_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    raw_last_status: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
