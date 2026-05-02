from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Banner(Base):
    __tablename__ = "banners"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    image: Mapped[str] = mapped_column(Text, nullable=False, default="")
    product_name: Mapped[dict] = mapped_column(JSONB, nullable=False)
    description: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    old_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sale_price: Mapped[int] = mapped_column(Integer, nullable=False)
    credit_months: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    link: Mapped[str] = mapped_column(String(255), nullable=False, default="/catalog")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
