from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class BoundCard(Base):
    """Atmos orqali biriktirilgan karta (saved card)."""

    __tablename__ = "bound_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Atmos qaytaradigan card_token (final, confirm dan keyin).
    # Pending_bind holatda hali None bo'ladi.
    card_token: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )
    # Atmos bind-card/init dan kelgan transaction_id (OTP confirm uchun)
    bind_transaction_id: Mapped[int | None] = mapped_column(
        BigInteger, unique=True, index=True, nullable=True
    )
    pan_masked: Mapped[str | None] = mapped_column(String(32), nullable=True)
    expiry: Mapped[str | None] = mapped_column(String(4), nullable=True)
    card_holder: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # pending_bind | active | removed | failed
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending_bind", server_default="pending_bind"
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
