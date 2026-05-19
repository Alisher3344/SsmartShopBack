"""Paymo skoring servisi: tashqi API javobini normallashtirish + jami hisoblash."""
from __future__ import annotations

import re
from typing import Any

from app.core.paymo import paymo
from app.schemas.scoring import CardScoringOut, MonthlyInflow

# "2021.06" formatdagi kalitlar
_MONTH_KEY = re.compile(r"^\d{4}\.\d{2}$")


def _parse_months(raw: dict[str, Any]) -> list[MonthlyInflow]:
    items: list[MonthlyInflow] = []
    for k, v in raw.items():
        if not isinstance(k, str) or not _MONTH_KEY.match(k):
            continue
        try:
            amt = int(v)
        except (TypeError, ValueError):
            continue
        items.append(MonthlyInflow(month=k, amount_tiyin=amt))
    # Yangidan eskigacha
    items.sort(key=lambda m: m.month, reverse=True)
    return items


async def get_card_scoring(card_token: str, *, include_raw: bool = False) -> CardScoringOut:
    """Karta tokeni bo'yicha 12 oylik tushum tarixi."""
    raw = await paymo.get_card_scoring(card_token)
    months = _parse_months(raw)
    total = sum(m.amount_tiyin for m in months)
    active = sum(1 for m in months if m.amount_tiyin > 0)
    avg = total // len(months) if months else 0
    return CardScoringOut(
        card_token=card_token,
        pan_masked=raw.get("pan"),
        holder_name=raw.get("holder_name"),
        bank=raw.get("bank"),
        phone=raw.get("phone"),
        months=months,
        total_tiyin=total,
        average_monthly_tiyin=avg,
        active_months=active,
        raw=raw if include_raw else None,
    )
