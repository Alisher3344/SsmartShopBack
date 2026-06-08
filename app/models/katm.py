"""KATM kredit byurosi integratsiyasi modellari.

KATMConsent — mijozning kredit-byuro roziligi (pAgreementId/pAgreementDate manbai).
              Har bir claim/report uchun MAJBURIY. Audit uchun immutable yozuv.
KATMRequest — har bir claim/report/ban chaqiruvi auditi + async report poll holati.
"""
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class KATMConsent(Base):
    __tablename__ = "katm_consents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # pAgreementId — KATM'ga yuboriladigan rozilik identifikatori (<=10 belgi)
    agreement_id: Mapped[str] = mapped_column(
        String(10), unique=True, nullable=False
    )
    # pAgreementDate — rozilik berilgan vaqt
    agreement_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Mijoz rozi bo'lgan matn (versiyalanadi)
    consent_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Rozilik nimani qamraydi: ["credit_report", "ban_check"]
    scope: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Rozilikni kim qayd etgan (admin)
    recorded_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class KATMRequest(Base):
    __tablename__ = "katm_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    consent_id: Mapped[int | None] = mapped_column(
        ForeignKey("katm_consents.id", ondelete="SET NULL"), nullable=True
    )
    # "credit_report" | "ban_check"
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    # Bizning generatsiya qilgan ID'larimiz (re-poll/dedupe uchun)
    claim_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    report_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # KATM-SIR snapshot
    katm_client_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # /credit/report 05050 holatida poll uchun Token
    report_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_format: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0 XML / 1 JSON
    # CREATED | CLAIM_OK | REPORT_PENDING | REPORT_READY | BAN_OK | ERROR
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="CREATED", server_default="CREATED", index=True
    )
    ban_status: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1/0
    result_code: Mapped[str | None] = mapped_column(String(8), nullable=True)  # data.result
    result_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Hisobot (format=1 bo'lsa report_decoded JSON; base64 audit uchun)
    report_base64: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_decoded: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Redact qilingan raw so'rov/javob snapshotlari (parol/PAN olib tashlangan)
    raw_claim: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    raw_report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_polled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
