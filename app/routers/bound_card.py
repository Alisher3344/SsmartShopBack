"""Saqlangan kartalar (Atmos bind-card) endpointlari."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.atmos import AtmosBusinessError, AtmosError
from app.db.database import get_db
from app.models.user import User
from app.routers.user import get_current_user
from app.schemas.bound_card import (
    BindCardConfirmIn,
    BindCardInitIn,
    BindCardInitOut,
    BoundCardOut,
)
from app.services import bound_card_service

router = APIRouter(prefix="/cards", tags=["cards"])


@router.get("", response_model=list[BoundCardOut], response_model_by_alias=True)
async def list_my_cards(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await bound_card_service.list_for_user(db, current_user)


@router.post(
    "/init",
    response_model=BindCardInitOut,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
async def bind_init(
    data: BindCardInitIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Atmos /partner/bind-card/init — OTP SMS karta egasining tel raqamiga jo'natiladi."""
    try:
        bound = await bound_card_service.init_bind(
            db, current_user, data.card_number, data.expiry
        )
    except AtmosBusinessError as e:
        raise HTTPException(status_code=400, detail=f"Atmos {e.code}: {e.description}")
    except AtmosError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return BindCardInitOut(
        bound_card_id=bound.id,
        bind_transaction_id=bound.bind_transaction_id or 0,
    )


@router.post("/confirm", response_model=BoundCardOut, response_model_by_alias=True)
async def bind_confirm(
    data: BindCardConfirmIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    bound = await bound_card_service.get_for_user(db, current_user, data.bound_card_id)
    if not bound:
        raise HTTPException(status_code=404, detail="Karta topilmadi")
    try:
        bound = await bound_card_service.confirm_bind(db, current_user, bound, data.otp)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except AtmosBusinessError as e:
        raise HTTPException(status_code=400, detail=f"Atmos {e.code}: {e.description}")
    except AtmosError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return bound


@router.delete("/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_card(
    card_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    bound = await bound_card_service.get_for_user(db, current_user, card_id)
    if not bound:
        raise HTTPException(status_code=404, detail="Karta topilmadi")
    try:
        await bound_card_service.remove(db, current_user, bound)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post(
    "/{card_id}/set-default",
    response_model=BoundCardOut,
    response_model_by_alias=True,
)
async def set_default_card(
    card_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    bound = await bound_card_service.get_for_user(db, current_user, card_id)
    if not bound:
        raise HTTPException(status_code=404, detail="Karta topilmadi")
    try:
        return await bound_card_service.set_default(db, current_user, bound)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
