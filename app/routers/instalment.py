"""Paymo rassrochka (instalment) endpoint'lari.

Mijoz uchun (doc'da yozilganidek):
  POST   /api/instalment            — order uchun rassrochka yaratish
  GET    /api/instalment/{id}       — bitta rassrochka + Paymo'dan status sync (polling)
  DELETE /api/instalment/{id}       — bekor qilish (mijoz NOT_CONFIRMED, admin har qachon)

Admin uchun (alohida doc):
  GET    /api/admin/instalment/transactions — Paymo /cmn/get-transactions
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ADMIN_ROLES, get_current_user, require_admin
from app.db.database import get_db
from app.models.user import User
from app.schemas.instalment import (
    PAYMENT_TYPE_LABELS,
    InstalmentCreateIn,
    InstalmentOut,
    TransactionsOut,
)
from app.services import instalment_service

log = logging.getLogger(__name__)

router = APIRouter(tags=["instalment"])


@router.post(
    "/instalment",
    response_model=InstalmentOut,
    status_code=201,
)
async def create_instalment(
    payload: InstalmentCreateIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Order'ga rassrochka biriktirib Paymo'da yaratadi.

    Order `payment_method=instalment` va `status=pending_payment` bo'lishi shart.
    User profili to'liq bo'lishi shart (passport, address, address_payer, work_place).
    """
    return await instalment_service.create_for_order(db, user, payload)


@router.get(
    "/instalment/{instalment_id}",
    response_model=InstalmentOut,
)
async def get_instalment(
    instalment_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    sync: bool = Query(True, description="Paymo'dan oxirgi statusni olib kelishmi"),
):
    """Bitta rassrochka. `sync=true` (default) bo'lsa Paymo'dan polling qiladi.

    Mijoz NOT_CONFIRMED holatdagi instalmentni har 5-10 sekundda polling qilishi
    mumkin. Status CONFIRMED/ACTIVE ga o'tganda Order avtomatik confirmed bo'ladi.
    """
    inst = await instalment_service.get_for_user(db, user, instalment_id)
    if sync:
        inst = await instalment_service.sync_status(db, inst)
    return inst


@router.delete(
    "/instalment/{instalment_id}",
    response_model=InstalmentOut,
)
async def cancel_instalment(
    instalment_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Rassrochkani bekor qilish.

    - Foydalanuvchi: faqat NOT_CONFIRMED holatda bekor qilishi mumkin.
    - Admin: har qanday holatda urinishi mumkin (Paymo'ning javobi qabul qilinadi).
    """
    inst = await instalment_service.get_for_user(db, user, instalment_id)
    is_admin = user.role in ADMIN_ROLES
    if not is_admin and inst.status != "NOT_CONFIRMED":
        raise HTTPException(
            status_code=400,
            detail=f"Faqat NOT_CONFIRMED holatda bekor qilish mumkin (hozir: {inst.status})",
        )
    return await instalment_service.cancel(db, inst)


@router.get(
    "/admin/instalment/by-paymo/{store_id}/{instalment_id}",
    dependencies=[Depends(require_admin)],
)
async def admin_get_paymo_instalment(
    store_id: int,
    instalment_id: int,
    _admin: User = Depends(require_admin),
):
    """Atmos store + rassrochka id bo'yicha bitta rassrochkani Paymo'dan oladi.

    Lokal jadvaldan emas — to'g'ridan-to'g'ri Atmos'dan, shuning uchun kassa/filial
    orqali ochilgan rassrochkalar ham ko'rinadi. Javob: raw Atmos dict
    (instalment_id, status, balance, file, holder, phone, ...).
    """
    return await instalment_service.get_paymo_instalment(store_id, instalment_id)


@router.get(
    "/admin/instalment/transactions",
    response_model=TransactionsOut,
    dependencies=[Depends(require_admin)],
)
async def admin_transactions(
    store_id: int = Query(..., description="Paymo store_id (stores.paymo_store_id)"),
    date_from: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    date_to: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    page: int | None = Query(None, ge=0),
    size: int | None = Query(None, ge=1, le=200),
    loan_id: int | None = Query(None),
    payment_id: int | None = Query(None),
    _admin: User = Depends(require_admin),
):
    """Paymo store bo'yicha to'lov yozuvlari (rassrochka payment log).

    Filter param'lari ixtiyoriy. Pagination 0-based. Javobda har bir
    payment uchun payment_type_label ham qaytadi (insoniy nom).
    """
    raw = await instalment_service.get_transactions(
        store_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        size=size,
        loan_id=loan_id,
        payment_id=payment_id,
    )
    # Doc javob shape'ini bizning schema'ga moslab + payment_type_label qo'shamiz
    payments = raw.get("payments") or []
    for p in payments:
        if isinstance(p, dict):
            p["payment_type_label"] = PAYMENT_TYPE_LABELS.get(p.get("payment_type"))
    return {
        "payments": payments,
        "totalPayments": raw.get("totalPayments"),
        "totalPages": raw.get("totalPages"),
        "currentPage": raw.get("currentPage"),
    }
