"""Paymo scoring schema'lari."""
from __future__ import annotations

from pydantic import BaseModel, Field


class MonthlyInflow(BaseModel):
    """Bir oydagi tushum (tiyinda)."""
    month: str = Field(..., description="YYYY.MM format")
    amount_tiyin: int = Field(..., description="Tushum summasi (tiyin)")


class CardScoringOut(BaseModel):
    """Karta 12 oylik tushum tarixi + meta."""
    card_token: str
    pan_masked: str | None = Field(None, description="PAN niqoblangan: XXXXXX******XXXX")
    holder_name: str | None = None
    bank: str | None = None
    phone: str | None = None
    # Tartiblangan oylar (yangidan eskigacha)
    months: list[MonthlyInflow]
    # Yig'indilar (kredit qarori uchun qulay)
    total_tiyin: int = Field(..., description="12 oydagi umumiy tushum (tiyin)")
    average_monthly_tiyin: int = Field(..., description="Oylik o'rtacha tushum (tiyin)")
    active_months: int = Field(..., description="Tushum bo'lgan oylar soni (0 dan katta)")
    # Raw javob (audit / debug uchun)
    raw: dict | None = None
