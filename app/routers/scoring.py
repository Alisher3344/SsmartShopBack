"""Paymo skoring endpoint'lari (faqat admin/superadmin).

Maqsad: kredit ofitser kartani Paymo /scoring/get-monthly orqali tekshirib,
mijozning to'lov qobiliyatini va mavjud kreditlarini baholaydi.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.deps import require_admin
from app.core.paymo import PaymoBusinessError, PaymoError
from app.models.user import User
from app.schemas.scoring import MonthlyScoringIn, MonthlyScoringOut
from app.services import scoring_service

log = logging.getLogger(__name__)

router = APIRouter(prefix="/scoring", tags=["scoring"])


@router.post(
    "/get-monthly",
    response_model=MonthlyScoringOut,
    dependencies=[Depends(require_admin)],
)
async def monthly_scoring(
    payload: MonthlyScoringIn,
    include_raw: bool = Query(False, description="Paymo raw javobini ham qaytarishmi"),
    _admin: User = Depends(require_admin),
):
    """Karta bo'yicha oylik tushum holatini Paymo'dan oladi.

    Javob: oy bo'yicha bool + bank + holder_name + debt_load (mavjud kreditlar).
    """
    try:
        return await scoring_service.get_monthly_scoring(
            payload.card_number,
            payload.card_expiry,
            payload.amount,
            payload.percent,
            include_raw=include_raw,
        )
    except PaymoBusinessError as e:
        raise HTTPException(status_code=400, detail=f"Paymo {e.code}: {e.description}")
    except PaymoError as e:
        raise HTTPException(status_code=502, detail=str(e))
