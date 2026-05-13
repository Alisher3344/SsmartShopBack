"""To'lov endpointlari (Atmos).

Oqim:
  1. POST /payments/init       — buyurtmaga to'lov sessiyasini boshlash
  2. POST /payments/pre-apply  — karta raqami yuborib SMS OTP so'rash
  3. POST /payments/apply      — OTP bilan tasdiqlash
  4. POST /payments/callback   — Atmos webhook (public, HMAC tekshiruvi)
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.atmos import AtmosBusinessError, AtmosError, atmos
from app.core.deps import require_admin
from app.db.database import get_db
from app.models.user import User
from app.routers.user import get_current_user
from app.schemas.payment import (
    PaymentApplyIn,
    PaymentInitIn,
    PaymentInitOut,
    PaymentOut,
    PaymentPreApplyIn,
    PaymentPreApplyOut,
    PaymentPreApplyTokenIn,
    RefundIn,
    RefundOut,
)
from app.services import bound_card_service, order_service, payment_service

log = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])


def _ensure_owner_or_admin(payment_user_id: int | None, current: User) -> None:
    if current.role in ("admin", "superadmin", "staff"):
        return
    if payment_user_id != current.id:
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")


@router.post("/init", response_model=PaymentInitOut, status_code=status.HTTP_201_CREATED)
async def init_payment(
    data: PaymentInitIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    order = await order_service.get_order(db, data.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
    if order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Bu sizning buyurtmangiz emas")
    try:
        payment = await payment_service.init_payment(db, current_user, order)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except AtmosBusinessError as e:
        raise HTTPException(status_code=400, detail=f"Atmos {e.code}: {e.description}")
    except AtmosError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return PaymentInitOut(
        payment_id=payment.id,
        atmos_transaction_id=payment.atmos_transaction_id or 0,
        amount_tiyin=payment.amount_tiyin,
        status=payment.status,
    )


@router.post("/pre-apply", response_model=PaymentPreApplyOut)
async def pre_apply(
    data: PaymentPreApplyIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    payment = await payment_service.get_payment(db, data.payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="To'lov topilmadi")
    _ensure_owner_or_admin(payment.user_id, current_user)
    try:
        payment = await payment_service.pre_apply(
            db, payment, card_number=data.card_number, expiry=data.expiry
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except AtmosBusinessError as e:
        raise HTTPException(status_code=400, detail=f"Atmos {e.code}: {e.description}")
    except AtmosError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return PaymentPreApplyOut(payment_id=payment.id, status=payment.status)


@router.post("/pre-apply-token", response_model=PaymentPreApplyOut)
async def pre_apply_with_token(
    data: PaymentPreApplyTokenIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Biriktirilgan karta (card_token) orqali pre-apply."""
    payment = await payment_service.get_payment(db, data.payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="To'lov topilmadi")
    _ensure_owner_or_admin(payment.user_id, current_user)
    # Token foydalanuvchining biriktirilgan kartasi ekanligini tekshiramiz
    bound = await bound_card_service.get_active_by_token_for_user(
        db, current_user, data.card_token
    )
    if not bound:
        raise HTTPException(status_code=400, detail="Bunday biriktirilgan karta yo'q")
    try:
        payment = await payment_service.pre_apply(
            db, payment, card_token=data.card_token
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except AtmosBusinessError as e:
        raise HTTPException(status_code=400, detail=f"Atmos {e.code}: {e.description}")
    except AtmosError as e:
        raise HTTPException(status_code=502, detail=str(e))
    # Karta ishlatildi — last_used_at yangilaymiz
    await bound_card_service.touch_last_used(db, bound)
    return PaymentPreApplyOut(payment_id=payment.id, status=payment.status)


@router.post("/apply", response_model=PaymentOut, response_model_by_alias=True)
async def apply_payment(
    data: PaymentApplyIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    payment = await payment_service.get_payment(db, data.payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="To'lov topilmadi")
    _ensure_owner_or_admin(payment.user_id, current_user)
    try:
        payment = await payment_service.apply(db, payment, data.otp)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except AtmosBusinessError as e:
        raise HTTPException(status_code=400, detail=f"Atmos {e.code}: {e.description}")
    except AtmosError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return payment


@router.get("/{payment_id}", response_model=PaymentOut, response_model_by_alias=True)
async def get_payment(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    payment = await payment_service.get_payment(db, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="To'lov topilmadi")
    _ensure_owner_or_admin(payment.user_id, current_user)
    return payment


@router.post("/callback", status_code=status.HTTP_200_OK)
async def atmos_callback(
    request: Request,
    x_signature: str | None = Header(default=None, alias="X-Signature"),
    db: AsyncSession = Depends(get_db),
):
    """Atmos webhook — HMAC-SHA256 X-SIGNATURE tekshiruvi.

    Public endpoint (auth talab qilinmaydi), lekin signature majburiy.
    """
    body = await request.body()
    if not atmos.verify_callback_signature(body, x_signature):
        log.warning("Atmos callback: noto'g'ri signature (%s)", x_signature)
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    payment = await payment_service.handle_callback(db, payload)
    if not payment:
        # Atmos qayta yubormasligi uchun 200 qaytaramiz, lekin loglaymiz
        log.warning("Atmos callback: payment topilmadi yoki ishlanmadi: %s", payload)
    return {"status": "success", "message": "Order processed"}


# ===== Admin endpointlari =====

@router.get(
    "/order/{order_id}/list",
    response_model=list[PaymentOut],
    response_model_by_alias=True,
)
async def list_order_payments(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Buyurtma uchun barcha to'lov urinishlari (egasi yoki admin)."""
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
    if current_user.role not in ("admin", "superadmin", "staff") and order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")
    from sqlalchemy import select
    from app.models.payment import PaymentTransaction
    res = await db.execute(
        select(PaymentTransaction)
        .where(PaymentTransaction.order_id == order_id)
        .order_by(PaymentTransaction.id.desc())
    )
    return list(res.scalars().all())


@router.post(
    "/{payment_id}/refund",
    response_model=RefundOut,
    response_model_by_alias=True,
    dependencies=[Depends(require_admin)],
)
async def refund_payment(
    payment_id: int,
    data: RefundIn,
    db: AsyncSession = Depends(get_db),
):
    """Admin: to'lovni qaytarish. amount_tiyin yuborilsa partial, bo'lmasa full."""
    payment = await payment_service.get_payment(db, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="To'lov topilmadi")
    try:
        payment, reverse_id = await payment_service.refund(
            db, payment, amount_tiyin=data.amount_tiyin
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except AtmosBusinessError as e:
        raise HTTPException(status_code=400, detail=f"Atmos {e.code}: {e.description}")
    except AtmosError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return RefundOut(
        payment_id=payment.id,
        refunded_tiyin=int(payment.refunded_tiyin or 0),
        payment_status=payment.status,
        reverse_id=reverse_id,
        atmos_status_code=payment.atmos_status_code,
        atmos_status_message=payment.atmos_status_message,
    )


@router.get(
    "",
    response_model=list[PaymentOut],
    response_model_by_alias=True,
    dependencies=[Depends(require_admin)],
)
async def list_all_payments(
    status_filter: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Adminlar uchun to'lovlar ro'yxati."""
    from sqlalchemy import select
    from app.models.payment import PaymentTransaction
    q = select(PaymentTransaction).order_by(PaymentTransaction.id.desc()).limit(200)
    if status_filter:
        q = q.where(PaymentTransaction.status == status_filter)
    res = await db.execute(q)
    return list(res.scalars().all())
