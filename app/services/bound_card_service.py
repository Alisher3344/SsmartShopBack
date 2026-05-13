"""Bind-card xizmati — Atmos /partner/bind-card/* endpointlari ustida."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.atmos import AtmosBusinessError, AtmosError, atmos
from app.models.bound_card import BoundCard
from app.models.user import User

log = logging.getLogger(__name__)


def _mask_pan(pan: str) -> str:
    """8600490744313347 -> 8600 **** **** 3347"""
    pan = pan.replace(" ", "")
    if len(pan) < 10:
        return pan
    return f"{pan[:4]} **** **** {pan[-4:]}"


async def list_for_user(db: AsyncSession, user: User) -> list[BoundCard]:
    res = await db.execute(
        select(BoundCard)
        .where(BoundCard.user_id == user.id, BoundCard.status == "active")
        .order_by(BoundCard.is_default.desc(), BoundCard.id.desc())
    )
    return list(res.scalars().all())


async def get_for_user(
    db: AsyncSession, user: User, card_id: int
) -> BoundCard | None:
    res = await db.execute(
        select(BoundCard).where(
            BoundCard.id == card_id, BoundCard.user_id == user.id
        )
    )
    return res.scalar_one_or_none()


async def get_active_by_token_for_user(
    db: AsyncSession, user: User, card_token: str
) -> BoundCard | None:
    res = await db.execute(
        select(BoundCard).where(
            BoundCard.card_token == card_token,
            BoundCard.user_id == user.id,
            BoundCard.status == "active",
        )
    )
    return res.scalar_one_or_none()


async def init_bind(
    db: AsyncSession, user: User, card_number: str, expiry: str
) -> BoundCard:
    """Atmos /partner/bind-card/init — pending yozuv yaratamiz, OTP SMS jo'natiladi."""
    bound = BoundCard(
        user_id=user.id,
        pan_masked=_mask_pan(card_number),
        expiry=expiry,
        status="pending_bind",
    )
    db.add(bound)
    await db.commit()
    await db.refresh(bound)

    try:
        resp = await atmos.bind_card_init(card_number, expiry)
    except (AtmosError, AtmosBusinessError) as e:
        bound.status = "failed"
        bound.updated_at = datetime.now(timezone.utc)
        await db.commit()
        raise

    tx_id = resp.get("transaction_id")
    if not tx_id:
        bound.status = "failed"
        bound.updated_at = datetime.now(timezone.utc)
        await db.commit()
        raise AtmosError(f"Atmos bind-card/init: transaction_id qaytarilmadi ({resp})")

    bound.bind_transaction_id = int(tx_id)
    bound.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(bound)
    return bound


async def confirm_bind(
    db: AsyncSession, user: User, bound: BoundCard, otp: str
) -> BoundCard:
    """Atmos /partner/bind-card/confirm — OTP bilan tasdiqlash, card_token saqlash."""
    if bound.user_id != user.id:
        raise ValueError("Ruxsat yo'q")
    if bound.status != "pending_bind":
        raise ValueError(f"confirm uchun mos status emas: {bound.status}")
    if not bound.bind_transaction_id:
        raise ValueError("bind_transaction_id yo'q — qayta init qiling")

    try:
        resp = await atmos.bind_card_confirm(bound.bind_transaction_id, otp)
    except (AtmosError, AtmosBusinessError):
        bound.status = "failed"
        bound.updated_at = datetime.now(timezone.utc)
        await db.commit()
        raise

    # Atmos javobida card_token va boshqa qo'shimcha maydonlar bo'lishi mumkin
    card_token = resp.get("card_token") or resp.get("token")
    if not card_token:
        # Ba'zi javoblarda card_id qaytishi mumkin — uni token sifatida saqlaymiz
        card_token = resp.get("card_id")
    if not card_token:
        bound.status = "failed"
        bound.updated_at = datetime.now(timezone.utc)
        await db.commit()
        raise AtmosError(f"Atmos bind-card/confirm: card_token yo'q ({resp})")

    bound.card_token = str(card_token)
    bound.card_holder = resp.get("card_holder") or resp.get("holder_name")
    bound.status = "active"
    bound.updated_at = datetime.now(timezone.utc)

    # Birinchi karta bo'lsa avto-default qilamiz
    res = await db.execute(
        select(BoundCard).where(
            BoundCard.user_id == user.id,
            BoundCard.status == "active",
            BoundCard.id != bound.id,
        )
    )
    has_other_active = res.scalar_one_or_none() is not None
    if not has_other_active:
        bound.is_default = True

    await db.commit()
    await db.refresh(bound)
    return bound


async def remove(db: AsyncSession, user: User, bound: BoundCard) -> None:
    """Atmos /partner/remove-card — token o'chiriladi, lokal yozuv 'removed' bo'ladi."""
    if bound.user_id != user.id:
        raise ValueError("Ruxsat yo'q")
    if bound.card_token:
        try:
            await atmos.remove_card(bound.card_token)
        except (AtmosError, AtmosBusinessError) as e:
            # Atmos tomonda o'chmasa ham lokal yozuvni o'chiramiz, lekin loglaymiz
            log.warning("Atmos remove_card xatosi (id=%s): %s", bound.id, e)
    bound.status = "removed"
    bound.is_default = False
    bound.updated_at = datetime.now(timezone.utc)
    await db.commit()


async def set_default(db: AsyncSession, user: User, bound: BoundCard) -> BoundCard:
    if bound.user_id != user.id or bound.status != "active":
        raise ValueError("Bu karta default sifatida belgilanmaydi")
    await db.execute(
        update(BoundCard)
        .where(BoundCard.user_id == user.id, BoundCard.id != bound.id)
        .values(is_default=False)
    )
    bound.is_default = True
    bound.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(bound)
    return bound


async def touch_last_used(db: AsyncSession, bound: BoundCard) -> None:
    bound.last_used_at = datetime.now(timezone.utc)
    bound.updated_at = bound.last_used_at
    await db.commit()
