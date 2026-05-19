"""Paymo skoring endpoint'lari (faqat admin/superadmin).

Maqsad: kredit ofitser karta tokeni bo'yicha 12 oylik tushum tarixini ko'rib
mijozning to'lov qobiliyatini baholaydi.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.deps import require_admin
from app.core.paymo import PaymoBusinessError, PaymoError
from app.models.user import User
from app.schemas.scoring import CardScoringOut
from app.services import scoring_service

log = logging.getLogger(__name__)

router = APIRouter(prefix="/scoring", tags=["scoring"])


@router.get(
    "/card/{card_token}",
    response_model=CardScoringOut,
    dependencies=[Depends(require_admin)],
)
async def card_scoring(
    card_token: str,
    include_raw: bool = Query(False, description="Paymo raw javobini ham qaytarishmi"),
    _admin: User = Depends(require_admin),
):
    """Karta tizim tokeni bo'yicha 12 oylik tushum tarixi (kredit skoring)."""
    try:
        return await scoring_service.get_card_scoring(card_token, include_raw=include_raw)
    except PaymoBusinessError as e:
        raise HTTPException(status_code=400, detail=f"Paymo {e.code}: {e.description}")
    except PaymoError as e:
        raise HTTPException(status_code=502, detail=str(e))
