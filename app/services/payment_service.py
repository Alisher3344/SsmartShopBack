"""To'lov xizmati — Atmos klienti ustida turuvchi domain qatlam.

Buyurtma → PaymentTransaction → Atmos chaqiruvlari → status yangilash.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.atmos import AtmosBusinessError, AtmosError, atmos
from app.models.order import Order
from app.models.payment import PaymentTransaction
from app.models.user import User
from app.services import order_service

log = logging.getLogger(__name__)


async def get_payment(db: AsyncSession, payment_id: int) -> PaymentTransaction | None:
    res = await db.execute(
        select(PaymentTransaction).where(PaymentTransaction.id == payment_id)
    )
    return res.scalar_one_or_none()


async def get_payment_by_atmos_id(
    db: AsyncSession, atmos_transaction_id: int
) -> PaymentTransaction | None:
    res = await db.execute(
        select(PaymentTransaction).where(
            PaymentTransaction.atmos_transaction_id == atmos_transaction_id
        )
    )
    return res.scalar_one_or_none()


async def init_payment(
    db: AsyncSession, user: User, order: Order
) -> PaymentTransaction:
    """Buyurtma uchun yangi to'lov sessiyasini boshlash.

    Atmos /merchant/pay/create chaqiriladi → atmos_transaction_id qaytariladi.
    Bir buyurtmaga bir nechta urinish (failed → yangi init) ruxsat.
    """
    if order.payment_status == "paid":
        raise ValueError("Bu buyurtma allaqachon to'langan")
    if order.payment_method != "card":
        raise ValueError("Faqat 'card' to'lov turi Atmos orqali to'lanadi")

    # account — buyurtma ID'si (Atmosga aniq identifikator sifatida yuboramiz)
    account = f"order-{order.id}"
    amount_tiyin = int(order.total) * 100  # so'm → tiyin

    payment = PaymentTransaction(
        order_id=order.id,
        user_id=user.id,
        account=account,
        amount_tiyin=amount_tiyin,
        status="draft",
    )
    db.add(payment)
    await db.commit()
    await db.refresh(payment)

    try:
        resp = await atmos.create_transaction(amount_tiyin=amount_tiyin, account=account)
    except (AtmosError, AtmosBusinessError) as e:
        await _mark_failed(db, payment, e, stage="create")
        raise

    atmos_tx_id = resp.get("transaction_id")
    if not atmos_tx_id:
        await _mark_failed(db, payment, RuntimeError("transaction_id yo'q"), stage="create")
        raise AtmosError(f"Atmos create: transaction_id qaytarilmadi ({resp})")

    payment.atmos_transaction_id = int(atmos_tx_id)
    payment.raw_response = resp
    payment.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(payment)
    return payment


async def pre_apply(
    db: AsyncSession,
    payment: PaymentTransaction,
    *,
    card_number: str | None = None,
    expiry: str | None = None,
    card_token: str | None = None,
) -> PaymentTransaction:
    """Karta ma'lumotlarini Atmosga yuborib OTP SMS jo'natishni so'rash."""
    if not payment.atmos_transaction_id:
        raise ValueError("Avval payment init qiling")
    if payment.status not in ("draft", "pending_otp", "failed"):
        raise ValueError(f"pre-apply uchun mos status emas: {payment.status}")

    try:
        if card_token:
            resp = await atmos.pre_apply_token(payment.atmos_transaction_id, card_token)
        else:
            assert card_number and expiry
            resp = await atmos.pre_apply(
                payment.atmos_transaction_id, card_number, expiry
            )
    except (AtmosError, AtmosBusinessError) as e:
        await _mark_failed(db, payment, e, stage="pre_apply")
        raise

    payment.status = "pending_otp"
    payment.raw_response = resp
    payment.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(payment)
    return payment


async def apply(
    db: AsyncSession, payment: PaymentTransaction, otp: str
) -> PaymentTransaction:
    """OTP bilan to'lovni yakuniy tasdiqlash."""
    if not payment.atmos_transaction_id:
        raise ValueError("Avval payment init qiling")
    if payment.status not in ("pending_otp", "draft"):
        raise ValueError(f"apply uchun mos status emas: {payment.status}")

    try:
        resp = await atmos.apply(payment.atmos_transaction_id, otp)
    except (AtmosError, AtmosBusinessError) as e:
        await _mark_failed(db, payment, e, stage="apply")
        raise

    store_tx = resp.get("store_transaction") or {}
    confirmed = bool(store_tx.get("confirmed"))
    payment.atmos_success_trans_id = store_tx.get("success_trans_id")
    payment.atmos_status_code = str(store_tx.get("status_code") or "")
    payment.atmos_status_message = store_tx.get("status_message")
    payment.card_id = store_tx.get("card_id")
    payment.ofd_url = resp.get("ofd_url")
    payment.ofd_url_commission = resp.get("ofd_url_commission")
    payment.raw_response = resp
    payment.updated_at = datetime.now(timezone.utc)

    if confirmed:
        payment.status = "confirmed"
        await db.commit()
        await db.refresh(payment)
        # Buyurtmani finalize qilamiz (transit_code generatsiya)
        order = await order_service.get_order(db, payment.order_id)
        if order:
            await order_service.finalize_after_payment(db, order)
    else:
        payment.status = "failed"
        await db.commit()
        await db.refresh(payment)
        order = await order_service.get_order(db, payment.order_id)
        if order:
            await order_service.mark_payment_failed(db, order)
    return payment


async def refund(
    db: AsyncSession,
    payment: PaymentTransaction,
    *,
    amount_tiyin: int | None = None,
) -> tuple[PaymentTransaction, int | None]:
    """To'lovni qaytarish. amount_tiyin=None → to'liq (full reverse).
    Aks holda — qisman (create-reverse-partial + confirm-reverse-partial).

    Qaytaradi: (payment, reverse_id) — reverse_id partial uchun Atmos qaytaradigan id.
    """
    if payment.status not in ("confirmed", "partially_refunded"):
        raise ValueError(
            f"Refund uchun mos status emas: {payment.status} (faqat confirmed/partially_refunded)"
        )
    if not payment.atmos_success_trans_id:
        raise ValueError("success_trans_id yo'q — Atmosda muvaffaqiyatli to'lov topilmadi")

    already_refunded = int(payment.refunded_tiyin or 0)
    remaining = int(payment.amount_tiyin) - already_refunded
    if remaining <= 0:
        raise ValueError("Bu to'lov to'liq qaytarilgan")

    is_full = amount_tiyin is None or amount_tiyin >= remaining
    refund_amount = remaining if is_full else int(amount_tiyin)
    reverse_id: int | None = None

    try:
        if is_full:
            resp = await atmos.reverse(payment.atmos_success_trans_id)
        else:
            init_resp = await atmos.create_reverse_partial(
                payment.atmos_success_trans_id, refund_amount
            )
            reverse_id = init_resp.get("reverse_id") or init_resp.get("id")
            if not reverse_id:
                raise AtmosError(
                    f"Atmos create-reverse-partial: reverse_id qaytarilmadi ({init_resp})"
                )
            resp = await atmos.confirm_reverse_partial(
                payment.atmos_success_trans_id, int(reverse_id)
            )
    except (AtmosError, AtmosBusinessError) as e:
        # Status'ni o'zgartirmaymiz — refund o'tmadi
        payment.atmos_status_message = f"[refund] {e}"
        payment.updated_at = datetime.now(timezone.utc)
        await db.commit()
        raise

    payment.refunded_tiyin = already_refunded + refund_amount
    payment.atmos_status_code = str(((resp or {}).get("result") or {}).get("code") or "")
    payment.atmos_status_message = ((resp or {}).get("result") or {}).get("description")
    payment.raw_response = resp
    payment.updated_at = datetime.now(timezone.utc)

    if is_full or payment.refunded_tiyin >= payment.amount_tiyin:
        payment.status = "refunded"
        await db.commit()
        await db.refresh(payment)
        # Buyurtmaga ham ko'rsatamiz
        order = await order_service.get_order(db, payment.order_id)
        if order:
            order.payment_status = "refunded"
            order.updated_at = datetime.now(timezone.utc)
            await db.commit()
    else:
        payment.status = "partially_refunded"
        await db.commit()
        await db.refresh(payment)
        order = await order_service.get_order(db, payment.order_id)
        if order and order.payment_status not in ("refunded",):
            order.payment_status = "partially_refunded"
            order.updated_at = datetime.now(timezone.utc)
            await db.commit()
    return payment, reverse_id


async def handle_callback(
    db: AsyncSession, payload: dict[str, Any]
) -> PaymentTransaction | None:
    """Atmos webhook — payment statusini yangilab, kerak bo'lsa orderni finalize qilamiz.

    Idempotent: bir xil callback bir necha marta kelsa ham bir martagina effekt qiladi.
    """
    atmos_tx_id = payload.get("transaction_id")
    if not atmos_tx_id:
        log.warning("Atmos callback: transaction_id yo'q (%s)", payload)
        return None
    payment = await get_payment_by_atmos_id(db, int(atmos_tx_id))
    if not payment:
        log.warning("Atmos callback: payment topilmadi (atmos_tx=%s)", atmos_tx_id)
        return None

    confirmed = bool(payload.get("confirmed"))
    payment.atmos_status_code = str(payload.get("status_code") or "")
    payment.atmos_status_message = payload.get("status_message")
    if payload.get("success_trans_id"):
        payment.atmos_success_trans_id = int(payload["success_trans_id"])
    if payload.get("card_id"):
        payment.card_id = payload["card_id"]
    payment.raw_response = payload
    payment.callback_received_at = datetime.now(timezone.utc)
    payment.updated_at = payment.callback_received_at

    # Idempotency — agar allaqachon confirmed bo'lsa, qayta finalize qilmaymiz
    already_confirmed = payment.status == "confirmed"

    if confirmed and not already_confirmed:
        payment.status = "confirmed"
        await db.commit()
        await db.refresh(payment)
        order = await order_service.get_order(db, payment.order_id)
        if order:
            await order_service.finalize_after_payment(db, order)
    elif not confirmed and payment.status not in ("confirmed", "refunded"):
        payment.status = "failed"
        await db.commit()
        await db.refresh(payment)
        order = await order_service.get_order(db, payment.order_id)
        if order and order.payment_status != "paid":
            await order_service.mark_payment_failed(db, order)
    else:
        # Hech narsa o'zgarmadi — faqat callback log
        await db.commit()
        await db.refresh(payment)
    return payment


# ===== Internal helpers =====

async def _mark_failed(
    db: AsyncSession,
    payment: PaymentTransaction,
    err: Exception,
    *,
    stage: str,
) -> None:
    code = ""
    message = str(err)
    if isinstance(err, AtmosBusinessError):
        code = str(err.code)
        message = err.description or message
    payment.status = "failed"
    payment.atmos_status_code = code
    payment.atmos_status_message = f"[{stage}] {message}"
    payment.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(payment)
