from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class PickupPoint(Base):
    __tablename__ = "pickup_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[dict] = mapped_column(JSONB, nullable=False)  # {uz, ru}
    address: Mapped[dict] = mapped_column(JSONB, nullable=False)  # {uz, ru}
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    work_hours: Mapped[str | None] = mapped_column(String(64), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
