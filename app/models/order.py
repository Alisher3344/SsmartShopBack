from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pickup_point_id: Mapped[int | None] = mapped_column(
        ForeignKey("pickup_points.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Buyurtma qaysi magazindan (mahsulot store_id'si asosida)
    store_id: Mapped[int | None] = mapped_column(
        ForeignKey("stores.id", ondelete="SET NULL"), nullable=True, index=True
    )
    delivery_type: Mapped[str] = mapped_column(String(16), nullable=False, default="pickup")
    delivery_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_method: Mapped[str] = mapped_column(String(16), nullable=False, default="card")
    # items: [{product_id, name (dict), qty, price, image}]
    items: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Buyurtma berilgan paytda foydalanuvchi ma'lumotlari (snapshot)
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", index=True
    )  # pending | pending_payment | confirmed | ready | delivered | cancelled
    # pending | paid | failed | refunded | partially_refunded
    payment_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending"
    )
    # 1-kod: sotuv admin tasdiqlasa beriladi, mahsulot bilan punktga jo'natiladi
    transit_code: Mapped[str | None] = mapped_column(
        String(16), unique=True, index=True, nullable=True
    )
    # 2-kod: punkt admin transit kodni qabul qilsa generatsiya, foydalanuvchiga yuboriladi
    pickup_code: Mapped[str | None] = mapped_column(
        String(16), unique=True, index=True, nullable=True
    )
    received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Admin mahsulot kodini (yorliq) chop etib punktga jo'natdi — doimiy belgi.
    # status `confirmed`ligicha qoladi; UI shu belgi bo'yicha kartochkani "hira" qiladi,
    # ikkinchi admin qayta qabul qilmasligi uchun.
    dispatched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    dispatched_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    dispatched_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
