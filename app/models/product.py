from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # Mahsulot qaysi magazinga tegishli
    store_id: Mapped[int | None] = mapped_column(
        ForeignKey("stores.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[dict] = mapped_column(JSONB, nullable=False)
    description: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    old_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    subcategory: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    # Erkin matn — masalan B/U mahsulotlarda holat tafsiloti (ixtiyoriy)
    condition_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    image: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Qo'shimcha rasmlar (asosiy + qo'shimchalar). Bo'sh bo'lsa faqat `image` ishlatiladi.
    images: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rating: Mapped[float] = mapped_column(Float, nullable=False, default=4.5)
    credit_months: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    delivery_days: Mapped[int] = mapped_column(Integer, nullable=False, default=3, server_default="3")
    badges: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    on_sale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Super admin qo'lda "Ommabop" ro'yxatiga qo'sha oladi
    specifications: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    is_popular: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
