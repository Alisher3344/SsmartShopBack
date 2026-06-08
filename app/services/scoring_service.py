"""Paymo skoring servisi: /scoring/get-monthly javobini normallashtirish."""
from __future__ import annotations

import re
from typing import Any

from app.core.paymo import paymo
from app.schemas.scoring import MonthlyScoringOut

# "2023.06" formatdagi kalitlar (yil.oy)
_MONTH_KEY = re.compile(r"^\d{4}\.\d{2}$")


def _extract_months(raw: dict[str, Any]) -> dict[str, bool]:
    """Raw javobdan faqat YYYY.MM kalitlarini ajratib boolean dict qaytaramiz."""
    out: dict[str, bool] = {}
    for k, v in raw.items():
        if isinstance(k, str) and _MONTH_KEY.match(k):
            out[k] = bool(v)
    return out


async def get_monthly_scoring(
    card_number: str,
    card_expiry: str,
    amount: int,
    percent: int,
    *,
    include_raw: bool = False,
) -> MonthlyScoringOut:
    """Karta bo'yicha oylik tushum holatini (true/false) Paymo'dan oladi.

    Javob: oy bo'yicha {bool} dict + bank + holder_name + debt_load.
    """
    raw = await paymo.get_monthly_scoring(card_number, card_expiry, amount, percent)
    months = _extract_months(raw)
    debt_load = raw.get("debt_load") or []
    if not isinstance(debt_load, list):
        debt_load = []
    return MonthlyScoringOut(
        months=months,
        debt_load=debt_load,
        bank=raw.get("bank"),
        holder_name=raw.get("holder_name"),
        raw=raw if include_raw else None,
    )
