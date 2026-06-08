from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Asosiy magazin (default). Faqat bitta bo'lishi mumkin (partial unique index).
    # Bu magazin o'chirilmaydi; mahsulot/buyurtmaning fallback joyi.
    is_main: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Paymo'da ro'yxatdan o'tgan store identifikatori (instalment yaratish uchun).
    # Har bir SsmartShop magazin Paymo'da o'z ID'iga ega bo'lishi mumkin; NULL bo'lsa
    # bu magazin orqali instalment yaratib bo'lmaydi.
    paymo_store_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
