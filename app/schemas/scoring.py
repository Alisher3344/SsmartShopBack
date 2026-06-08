"""Paymo scoring schema'lari (POST /scoring/get-monthly)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class MonthlyScoringIn(BaseModel):
    """Paymo /scoring/get-monthly so'rovi."""

    card_number: str = Field(..., min_length=16, max_length=19, description="Karta PAN")
    card_expiry: str = Field(
        ..., pattern=r"^\d{4}$", description="YYMM format, masalan: 2509"
    )
    amount: int = Field(..., gt=0, description="Kredit summasi (tiyin)")
    percent: int = Field(..., ge=0, le=100, description="Foiz stavkasi (butun son)")


class MonthlyScoringOut(BaseModel):
    """Paymo /scoring/get-monthly javobi.

    `months` — "YYYY.MM" -> bool dict (oy davomida karta egasiga pul tushganmi).
    """

    months: dict[str, bool] = Field(default_factory=dict)
    debt_load: list = Field(default_factory=list, description="Mavjud kreditlar")
    bank: str | None = None
    holder_name: str | None = None
    raw: dict | None = None
