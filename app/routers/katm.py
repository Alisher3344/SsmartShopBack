"""KATM kredit byurosi endpoint'lari (faqat admin/superadmin).

Maqsad: kredit ofitser mijozga rassrochka berishdan oldin uning kredit tarixini
(/credit-check) va kreditlash taqiqini (/ban-check) KATM orqali tekshiradi.
Har bir claim/report uchun mijoz roziligi (/consent) MAJBURIY.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_admin
from app.core.katm import KATMBusinessError, KATMError
from app.db.database import get_db
from app.models.user import User
from app.schemas.katm import (
    BanStatusOut,
    ConsentIn,
    ConsentOut,
    CreditCheckIn,
    CreditReportOut,
)
from app.services import katm_service

log = logging.getLogger(__name__)

router = APIRouter(prefix="/katm", tags=["katm"])


@router.post("/consent", response_model=ConsentOut, dependencies=[Depends(require_admin)])
async def create_consent(
    payload: ConsentIn,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Mijoz kredit-byuro roziligini qayd etish (agreement_id + sana generatsiya)."""
    user = await db.get(User, payload.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
    return await katm_service.record_consent(
        db, user,
        consent_text=payload.consent_text,
        scope=payload.scope,
        recorded_by=admin.id,
    )


@router.get(
    "/consent/{user_id}",
    response_model=ConsentOut | None,
    dependencies=[Depends(require_admin)],
)
async def active_consent(
    user_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Foydalanuvchining faol (revoke qilinmagan) roziligi."""
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
    return await katm_service.get_active_consent(db, user)


@router.post(
    "/credit-check",
    response_model=CreditReportOut,
    dependencies=[Depends(require_admin)],
)
async def credit_check(
    payload: CreditCheckIn,
    db: AsyncSession = Depends(get_db),
):
    """Claim ro'yxati + kredit hisoboti. Hisobot tayyor bo'lmasa (05050) status="pending"
    va token qaytadi — klient /credit-report/{request_id} orqali poll qiladi."""
    try:
        return await katm_service.credit_check(db, payload)
    except KATMBusinessError as e:
        raise HTTPException(status_code=400, detail=f"KATM {e.code}: {e.message}")
    except KATMError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get(
    "/credit-report/{request_id}",
    response_model=CreditReportOut,
    dependencies=[Depends(require_admin)],
)
async def poll_credit_report(
    request_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Pending (05050) hisobotni tekshirish (>=60s interval server tomonda ushlanadi)."""
    try:
        return await katm_service.poll_report(db, request_id)
    except KATMBusinessError as e:
        raise HTTPException(status_code=400, detail=f"KATM {e.code}: {e.message}")
    except KATMError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post(
    "/ban-check",
    response_model=BanStatusOut,
    dependencies=[Depends(require_admin)],
)
async def ban_check(
    user_id: int | None = Query(default=None, description="Foydalanuvchi ID (PINFL undan olinadi)"),
    pinfl: str | None = Query(default=None, description="To'g'ridan-to'g'ri PINFL (14 raqam)"),
    db: AsyncSession = Depends(get_db),
):
    """Kreditlash taqiqi reyestrida mijoz bor-yo'qligini tekshiradi (mustaqil)."""
    if user_id is None and not pinfl:
        raise HTTPException(status_code=422, detail="user_id yoki pinfl bering")
    try:
        return await katm_service.ban_check(db, user_id=user_id, pinfl=pinfl)
    except KATMBusinessError as e:
        raise HTTPException(status_code=400, detail=f"KATM {e.code}: {e.message}")
    except KATMError as e:
        raise HTTPException(status_code=502, detail=str(e))
