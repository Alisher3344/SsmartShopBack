"""Paymo rassrochka (instalment) servisi.

Asosiy oqim:
  1. create_for_order — Paymo'da rassrochka yaratamiz, lokalga saqlaymiz (NOT_CONFIRMED).
  2. sync_status — Paymo GET orqali statusni yangilaymiz; CONFIRMED/ACTIVE bo'lsa
     order_service.finalize_after_payment chaqiramiz.
  3. cancel — Paymo DELETE + lokal CANCELLED + buyurtmani bekor qilamiz.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.paymo import PaymoBusinessError, PaymoError, paymo
from app.models.instalment import Instalment
from app.models.order import Order
from app.models.store import Store
from app.models.user import User
from app.schemas.instalment import InstalmentCreateIn
from app.services import order_service

log = logging.getLogger(__name__)

# Paymo status — Order finalize qilinishi kerak (kreditga sotish faollashdi).
_CONFIRMED_STATUSES = {"CONFIRMED", "ACTIVE", "CLOSED"}
# Paymo status — buyurtma bekor qilinishi kerak.
_CANCELLED_STATUSES = {"CANCELLED", "FAILED", "REJECTED"}


def _redact_card(payload: dict[str, Any]) -> dict[str, Any]:
    """Audit uchun saqlanadigan payload'dan PAN va PIN'ni mask qilamiz."""
    out = dict(payload)
    pan = out.get("card_number") or ""
    if pan:
        out["card_number"] = "****" + str(pan)[-4:]
    if "pin" in out:
        out["pin"] = "***"
    return out


async def _get_store(db: AsyncSession, store_id: int | None) -> Store | None:
    if store_id is None:
        return None
    return await db.get(Store, store_id)


async def _existing_instalment_for_order(
    db: AsyncSession, order_id: int
) -> Instalment | None:
    res = await db.execute(
        select(Instalment).where(Instalment.order_id == order_id)
    )
    return res.scalar_one_or_none()


def _split_name(user: User) -> tuple[str, str, str]:
    """User.full_name -> (first, last, middle). middlename ustun bo'lsa undan tortamiz."""
    parts = (user.full_name or "").strip().split()
    first = parts[0] if parts else ""
    last = parts[1] if len(parts) > 1 else ""
    middle = (user.middlename or "").strip()
    if not middle and len(parts) > 2:
        middle = " ".join(parts[2:])
    return first, last, middle


def _build_paymo_payload(
    user: User,
    store: Store,
    payload: InstalmentCreateIn,
) -> dict[str, Any]:
    first, last, middle = _split_name(user)
    return {
        "store_id": store.paymo_store_id,
        "card_number": payload.card_number,
        "card_expiry": payload.card_expiry,
        "total_amount": payload.total_amount,
        "initial_amount": payload.initial_amount,
        "period": payload.period,
        "start_month": payload.start_month,
        "pay_day": payload.pay_day,
        "details": payload.details or "",
        "contract": payload.contract or "",
        "passport": user.passport or "",
        "address": user.address or "",
        "payer_name": first,
        "payer_lastname": last,
        "payer_middlename": middle,
        "payer_phone": user.phone or "",
        "debit_initial_amount": payload.debit_initial_amount,
        # Polling oqimida Paymo SMS orqali tasdiqlatadi
        "confirm_by_sms": True,
        "pin": user.passport or "",  # PINFL aynan passport bilan bir xil
        "address_payer": user.address_payer or user.address or "",
        "payer_work_place": user.work_place or "",
        "responsible_manager": payload.responsible_manager or "",
        "additional_number": payload.additional_number or "",
    }


def _validate_user_kyc(user: User) -> None:
    missing = [
        f for f in ("passport", "address", "address_payer", "work_place")
        if not getattr(user, f)
    ]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=(
                "Instalment yaratish uchun profil to'liq emas. "
                f"Yetishmayotgan maydonlar: {', '.join(missing)}"
            ),
        )
    if not user.phone:
        raise HTTPException(status_code=422, detail="Profilda telefon yo'q")
    if not (user.full_name and len(user.full_name.split()) >= 2):
        raise HTTPException(
            status_code=422,
            detail="Profilda ism va familiya to'liq emas (full_name)",
        )


async def create_for_order(
    db: AsyncSession, user: User, payload: InstalmentCreateIn
) -> Instalment:
    """Order'ga bog'lab Paymo'da rassrochka yaratadi."""
    order = await db.get(Order, payload.order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
    if order.user_id != user.id:
        raise HTTPException(status_code=403, detail="Bu buyurtma sizniki emas")
    if order.payment_method != "instalment":
        raise HTTPException(
            status_code=400,
            detail="Buyurtma payment_method != 'instalment'",
        )
    if order.status != "pending_payment":
        raise HTTPException(
            status_code=400,
            detail=f"Buyurtma holati {order.status}, instalment yaratib bo'lmaydi",
        )

    existing = await _existing_instalment_for_order(db, order.id)
    if existing and existing.status not in _CANCELLED_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Bu buyurtma uchun allaqachon instalment bor (status={existing.status})",
        )

    store = await _get_store(db, order.store_id)
    if store is None or store.paymo_store_id is None:
        raise HTTPException(
            status_code=422,
            detail="Buyurtmaning magazini Paymo'ga ulanmagan (paymo_store_id NULL)",
        )

    _validate_user_kyc(user)

    paymo_payload = _build_paymo_payload(user, store, payload)
    try:
        raw = await paymo.create_instalment(paymo_payload)
    except PaymoBusinessError as e:
        raise HTTPException(status_code=400, detail=f"Paymo {e.code}: {e.description}")
    except PaymoError as e:
        raise HTTPException(status_code=502, detail=str(e))

    # Mavjud CANCELLED yozuv bo'lsa o'rnini qayta ishlatamiz (unique order_id)
    instalment = existing or Instalment(order_id=order.id, user_id=user.id)
    instalment.store_id = store.id
    instalment.paymo_store_id = store.paymo_store_id
    instalment.paymo_instalment_id = (
        str(raw.get("instalment_id")) if raw.get("instalment_id") is not None else None
    )
    instalment.status = (raw.get("status") or "NOT_CONFIRMED").upper()
    instalment.card_last4 = payload.card_number[-4:]
    instalment.card_expiry = payload.card_expiry
    instalment.total_amount = payload.total_amount
    instalment.initial_amount = payload.initial_amount
    instalment.period = payload.period
    instalment.start_month = payload.start_month
    instalment.pay_day = payload.pay_day
    instalment.holder_name = raw.get("holder_name") or (
        f"{raw.get('first_name', '')} {raw.get('last_name', '')}".strip() or None
    )
    instalment.bank = raw.get("bank")
    instalment.phone_number = raw.get("phone_number") or user.phone
    instalment.balance = raw.get("balance")
    instalment.offer = raw.get("offer")
    instalment.raw_create_response = {
        "request": _redact_card(paymo_payload),
        "response": raw,
    }
    instalment.updated_at = datetime.now(timezone.utc)

    if existing is None:
        db.add(instalment)
    await db.commit()
    await db.refresh(instalment)

    # Agar Paymo darhol ACTIVE qaytarsa (kamdan-kam), order'ni darhol finalize qilamiz
    if instalment.status in _CONFIRMED_STATUSES:
        await order_service.finalize_after_payment(db, order)

    return instalment


async def sync_status(db: AsyncSession, instalment: Instalment) -> Instalment:
    """Paymo'dan oxirgi statusni olib lokalga yangilash + Order lifecycle."""
    if instalment.paymo_instalment_id is None or instalment.paymo_store_id is None:
        return instalment

    try:
        raw = await paymo.get_instalment(
            instalment.paymo_store_id, instalment.paymo_instalment_id
        )
    except PaymoBusinessError as e:
        raise HTTPException(status_code=400, detail=f"Paymo {e.code}: {e.description}")
    except PaymoError as e:
        raise HTTPException(status_code=502, detail=str(e))

    new_status = (raw.get("status") or instalment.status).upper()
    instalment.status = new_status
    instalment.contract_file_url = raw.get("file") or instalment.contract_file_url
    instalment.balance = raw.get("balance")
    instalment.offer = raw.get("offer")
    if raw.get("phone_number"):
        instalment.phone_number = raw.get("phone_number")
    instalment.raw_last_status = raw
    instalment.status_synced_at = datetime.now(timezone.utc)
    instalment.updated_at = datetime.now(timezone.utc)

    order = await db.get(Order, instalment.order_id)

    if new_status in _CONFIRMED_STATUSES and order is not None:
        await order_service.finalize_after_payment(db, order)
    elif new_status in _CANCELLED_STATUSES and order is not None:
        if order.status != "cancelled":
            await order_service.restore_stock(db, order)
            order.status = "cancelled"
            order.cancel_reason = order.cancel_reason or "instalment_cancelled"
            order.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(instalment)
    return instalment


async def cancel(db: AsyncSession, instalment: Instalment) -> Instalment:
    """Paymo'da rassrochkani bekor qilish + lokal status + Order cancel."""
    if instalment.paymo_instalment_id is None or instalment.paymo_store_id is None:
        # Hali Paymo'ga yuborilmagan — lokal CANCELLED qilamiz
        instalment.status = "CANCELLED"
        instalment.updated_at = datetime.now(timezone.utc)
    else:
        try:
            raw = await paymo.cancel_instalment(
                instalment.paymo_store_id, instalment.paymo_instalment_id
            )
        except PaymoBusinessError as e:
            raise HTTPException(
                status_code=400, detail=f"Paymo {e.code}: {e.description}"
            )
        except PaymoError as e:
            raise HTTPException(status_code=502, detail=str(e))
        instalment.status = "CANCELLED"
        instalment.raw_last_status = raw
        instalment.status_synced_at = datetime.now(timezone.utc)
        instalment.updated_at = datetime.now(timezone.utc)

    order = await db.get(Order, instalment.order_id)
    if order is not None and order.status != "cancelled":
        await order_service.restore_stock(db, order)
        order.status = "cancelled"
        order.cancel_reason = order.cancel_reason or "instalment_cancelled"
        order.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(instalment)
    return instalment


async def get_for_user(
    db: AsyncSession, user: User, instalment_id: int
) -> Instalment:
    inst = await db.get(Instalment, instalment_id)
    if inst is None:
        raise HTTPException(status_code=404, detail="Instalment topilmadi")
    is_admin = user.role in ("admin", "superadmin", "staff")
    if not is_admin and inst.user_id != user.id:
        raise HTTPException(status_code=403, detail="Bu instalment sizniki emas")
    return inst


async def get_paymo_instalment(store_id: int, instalment_id: int | str) -> dict:
    """Atmos store + instalment id bo'yicha bitta rassrochkani Paymo'dan oladi.

    Admin uchun: lokal `instalments` jadvalidan emas, to'g'ridan-to'g'ri Atmos'dan
    (kassa/filiallardan ochilganlar ham ko'rinadi). Javob raw Atmos dict.
    """
    try:
        return await paymo.get_instalment(store_id, instalment_id)
    except PaymoBusinessError as e:
        raise HTTPException(status_code=400, detail=f"Paymo {e.code}: {e.description}")
    except PaymoError as e:
        raise HTTPException(status_code=502, detail=str(e))


async def get_transactions(
    store_id: int,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int | None = None,
    size: int | None = None,
    loan_id: int | None = None,
    payment_id: int | None = None,
) -> dict:
    """Paymo /instalment/cmn/get-transactions — store bo'yicha to'lov hisoboti."""
    try:
        raw = await paymo.get_transactions(
            store_id,
            date_from=date_from,
            date_to=date_to,
            page=page,
            size=size,
            loan_id=loan_id,
            payment_id=payment_id,
        )
    except PaymoBusinessError as e:
        raise HTTPException(status_code=400, detail=f"Paymo {e.code}: {e.description}")
    except PaymoError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return raw
