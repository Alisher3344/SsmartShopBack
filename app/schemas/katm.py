"""KATM kredit byurosi endpoint'lari uchun pydantic schemalar."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ConsentIn(BaseModel):
    """Mijoz kredit-byuro roziligini qayd etish."""
    user_id: int
    consent_text: str | None = None
    scope: list[str] = Field(default_factory=lambda: ["credit_report", "ban_check"])


class ConsentOut(BaseModel):
    id: int
    user_id: int
    agreement_id: str
    agreement_date: datetime
    scope: list[str] | None = None
    revoked_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class CreditCheckIn(BaseModel):
    """Claim ro'yxati + kredit hisoboti so'rovi."""
    user_id: int
    lang: str = Field("ru", pattern=r"^(ru|uz|en)$")
    report_format: int = Field(1, ge=0, le=1, description="0 XML, 1 JSON")
    # MyID'da yo'q bo'lsa qo'lda override
    region: str | None = Field(None, max_length=2)
    local_region: str | None = Field(None, max_length=3)
    credit_amount: int | None = Field(
        None, ge=0, description="tiyin; berilmasa Instalment'dan olinadi"
    )
    credit_end_date: str | None = Field(
        None, description="yyyy-MM-dd; berilmasa Instalment'dan hisoblanadi"
    )
    # Faol rozilik bo'lmasa shu yerda yaratish
    create_consent: bool = False
    consent_text: str | None = None


class CreditReportOut(BaseModel):
    request_id: int
    status: str = Field(description='"ready" | "pending"')
    katm_client_id: str | None = None
    token: str | None = Field(None, description="pending holatida poll uchun")
    poll_after_seconds: int | None = None
    report: dict | None = Field(None, description="format=1 da decode qilingan JSON")
    report_base64: str | None = Field(None, description="format=0 (XML) yoki raw")
    result_code: str | None = None
    result_message: str | None = None


class BanStatusOut(BaseModel):
    pinfl: str
    status: int = Field(description="1 taqiq aktiv, 0 yo'q")
    banned: bool


class MyCreditCheckOut(BaseModel):
    """Foydalanuvchi "Limitni bilish" oqimi natijasi (mobil, self-service).

    Limit hozircha hisoblanmaydi — faqat tarix + taqiq qaytadi.
    """
    myid_verified: bool
    banned: bool
    ban_status: int
    # taqiq bo'lsa credit None (hisobot so'ralmaydi)
    credit: CreditReportOut | None = None
