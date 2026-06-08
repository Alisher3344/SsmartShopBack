"""KATM "Limitni bilish" — mobil self-service endpoint'lari (Flutter APK uchun).

Mounted at `/api/mobile/katm/*` (mobile_app sub-app ichida). Bearer talab qiladi —
natija current_user uchun.

Oqim (foydalanuvchi "Limitni bilish" tugmasini bosadi):
  1. POST /api/mobile/katm/credit-history
     - MyID tasdiqlanmagan bo'lsa 428 -> frontend avval MyID skaniga yo'naltiradi
     - taqiq tekshiruvi + kredit tarixi (rozilik avtomatik yoziladi)
     - hisobot tayyor bo'lmasa credit.status="pending" + request_id qaytadi
  2. GET /api/mobile/katm/credit-history/{request_id}
     - pending hisobotni poll qilish (>=60s)

Limit BU BOSQICHDA hisoblanmaydi — faqat tarix qaytadi. Limit logikasi keyingi qadam.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.katm import KATMBusinessError, KATMError
from app.db.database import get_db
from app.models.user import User
from app.schemas.katm import CreditReportOut, MyCreditCheckOut
from app.services import katm_service

log = logging.getLogger(__name__)

router = APIRouter(prefix="/katm", tags=["mobile"])


@router.post(
    "/credit-history",
    response_model=MyCreditCheckOut,
    summary="Limitni bilish — kredit tarixini olish",
    description=(
        "Current user uchun KATM taqiq tekshiruvi + kredit tarixini oladi. "
        "MyID tasdiqlanmagan bo'lsa 428 qaytadi (avval MyID kerak). Hisobot "
        "darhol tayyor bo'lmasa credit.status='pending' va request_id qaytadi — "
        "GET /credit-history/{request_id} orqali poll qiling."
    ),
)
async def my_credit_history(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MyCreditCheckOut:
    try:
        ban, credit = await katm_service.my_credit_history(db, user)
    except KATMBusinessError as e:
        raise HTTPException(status_code=400, detail=f"KATM {e.code}: {e.message}")
    except KATMError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return MyCreditCheckOut(
        myid_verified=True,
        banned=ban.banned,
        ban_status=ban.status,
        credit=credit,
    )


@router.get(
    "/credit-history/{request_id}",
    response_model=CreditReportOut,
    summary="Kredit tarixini poll qilish (pending bo'lsa)",
)
async def poll_my_credit_history(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CreditReportOut:
    try:
        return await katm_service.poll_report_for_user(db, request_id, user)
    except KATMBusinessError as e:
        raise HTTPException(status_code=400, detail=f"KATM {e.code}: {e.message}")
    except KATMError as e:
        raise HTTPException(status_code=502, detail=str(e))
