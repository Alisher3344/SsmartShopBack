from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class PaymentTransaction(Base):
    """Bitta buyurtmaga bir nechta to'lov urinishi bo'lishi mumkin
    (e.g. birinchi marta noto'g'ri karta — yangi PaymentTransaction yaratiladi).
    """

    __tablename__ = "payment_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Atmos qaytaradigan dastlabki transaction_id (create dan keyin)
    atmos_transaction_id: Mapped[int | None] = mapped_column(
        BigInteger, unique=True, index=True, nullable=True
    )
    # Atmos apply muvaffaqiyatli bo'lganda beriladigan id (refund uchun kerak)
    atmos_success_trans_id: Mapped[int | None] = mapped_column(
        BigInteger, unique=True, index=True, nullable=True
    )
    account: Mapped[str] = mapped_column(String(64), nullable=False)
    amount_tiyin: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Hozirgacha qaytarilgan summa (partial refundlar yig'indisi). 0 = qaytarilmagan.
    refunded_tiyin: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    # draft | pending_otp | confirmed | failed | refunded | partially_refunded | cancelled
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="draft", index=True
    )
    atmos_status_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    atmos_status_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    card_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ofd_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    ofd_url_commission: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Oxirgi Atmos javobi (audit/diagnostika uchun)
    raw_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    callback_received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
