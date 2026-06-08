from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # phone null bo'lmagan qatorlar uchun unique (migration 0004 qo'shgan)
        Index(
            "ux_users_phone_not_null",
            "phone",
            unique=True,
            postgresql_where=text("phone IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # Telegram orqali ro'yxatdan o'tganlar uchun email/password bo'lmasligi mumkin
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    username: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(32), default="user", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Telegram fieldlari
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, index=True, nullable=True)
    telegram_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Paymo instalment uchun KYC ma'lumotlari (bir marta to'ldirilib qayta ishlatiladi)
    passport: Mapped[str | None] = mapped_column(String(14), nullable=True)  # PINFL/JSHSHIR
    middlename: Mapped[str | None] = mapped_column(String(120), nullable=True)
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    address_payer: Mapped[str | None] = mapped_column(String(512), nullable=True)
    work_place: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # MyID identifikatsiyasi (passport bilan bir xil emas: MyID o'z ichki ID qaytaradi)
    myid_passport_serial: Mapped[str | None] = mapped_column(String(16), nullable=True)
    myid_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # SDK new flow uchun qayta foydalanish identifikatori (reusable unique id)
    myid_reuid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    myid_reuid_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # MyID yuz solishtirish reytingi (0.000-1.000), oxirgi muvaffaqiyatli skan
    myid_comparison_value: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 3), nullable=True
    )
    # MyID `/sdk/data` dan kelgan to'liq JSON — kelajakda scoring/audit uchun
    myid_raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # KATM kredit byurosi — bir marta aniqlanib qayta ishlatiladigan identifikatorlar
    katm_client_id: Mapped[str | None] = mapped_column(String(32), nullable=True)  # KATM-SIR
    katm_doc_series: Mapped[str | None] = mapped_column(String(5), nullable=True)
    katm_doc_number: Mapped[str | None] = mapped_column(String(10), nullable=True)
    katm_doc_type: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0 ID / 6 bio
    katm_region: Mapped[str | None] = mapped_column(String(2), nullable=True)  # SOATO viloyat
    katm_local_region: Mapped[str | None] = mapped_column(String(3), nullable=True)  # SOATO tuman
    # pickup_admin uchun - qaysi punktga biriktirilgan
    pickup_point_id: Mapped[int | None] = mapped_column(
        ForeignKey("pickup_points.id", ondelete="SET NULL"), nullable=True
    )
    # sales_admin uchun - qaysi magazinga biriktirilgan
    store_id: Mapped[int | None] = mapped_column(
        ForeignKey("stores.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
