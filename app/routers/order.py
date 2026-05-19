from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_admin
from app.db.database import get_db
from app.models.user import User
from app.routers.user import get_current_user
from app.schemas.order import CancelOrderIn, OrderCreate, OrderOut
from app.services import order_service, store_service

router = APIRouter(prefix="/orders", tags=["orders"])


async def _serialize(db: AsyncSession, order, viewer: User | None = None) -> dict:
    p_name, p_addr = await order_service.get_pickup_point_info(db, order.pickup_point_id)
    out = OrderOut.model_validate(order).model_dump(by_alias=True)
    out["pickupPointName"] = p_name
    out["pickupPointAddress"] = p_addr

    # transit_code rolga qarab maskalash:
    #   - superadmin barcha order'ning kodini ko'radi
    #   - staff faqat o'z magazinining order kodini ko'radi
    #   - sotuv admin (admin) faqat asosiy magazin order kodini ko'radi
    if viewer is not None and order.transit_code:
        if viewer.role == "superadmin":
            pass  # ko'radi
        elif viewer.role == "staff":
            if order.store_id != viewer.store_id:
                out["transitCode"] = None
        elif viewer.role == "admin":
            main_id = await store_service.get_main_store_id(db)
            if order.store_id != main_id:
                out["transitCode"] = None
        else:
            out["transitCode"] = None
    return out


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_order(
    data: OrderCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        order = await order_service.create_order(db, user, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return await _serialize(db, order, viewer=user)


@router.get("/my")
async def my_orders(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    orders = await order_service.list_user_orders(db, user.id)
    return [await _serialize(db, o, viewer=user) for o in orders]


@router.get("")
async def list_orders(
    pickup_point_id: int | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Buyurtmalar ro'yxati:
       - superadmin: barchasini
       - staff (magazin admin): faqat o'z magazinining buyurtmalari
       - admin (sotuv admin): asosiy magazin (is_main) buyurtmalari
    """
    store_filter = None
    only_no_store = False
    if user.role == "staff":
        if not user.store_id:
            return []
        store_filter = user.store_id
    elif user.role == "admin":
        main_id = await store_service.get_main_store_id(db)
        if main_id is None:
            return []
        store_filter = main_id
    orders = await order_service.list_orders_for_admin(
        db,
        pickup_point_id=pickup_point_id,
        status=status_filter,
        store_id=store_filter,
        only_no_store=only_no_store,
    )
    return [await _serialize(db, o, viewer=user) for o in orders]


@router.post("/{order_id}/confirm")
async def confirm_order(
    order_id: int,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
    # Staff (magazin admin) faqat o'z magazinining buyurtmasini boshqara oladi
    if user.role == "staff" and order.store_id != user.store_id:
        raise HTTPException(status_code=403, detail="Bu buyurtma boshqa magazinga tegishli")
    if order.status != "pending":
        raise HTTPException(status_code=400, detail="Faqat kutilayotgan buyurtmalarni tasdiqlash mumkin")
    order = await order_service.confirm_with_transit_code(db, order)
    return await _serialize(db, order, viewer=user)


@router.post("/{order_id}/cancel")
async def cancel_order(
    order_id: int,
    payload: CancelOrderIn | None = Body(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
    # Admin/super/staff yoki egasi bekor qila oladi
    is_owner = order.user_id == current_user.id
    is_admin = current_user.role in ("admin", "superadmin")
    is_store_staff = (
        current_user.role == "staff"
        and order.store_id == current_user.store_id
    )
    if not (is_owner or is_admin or is_store_staff):
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")
    if order.status == "cancelled":
        return await _serialize(db, order, viewer=current_user)
    # Faqat avval cancel qilinmagan bo'lsa stock qaytariladi
    await order_service.restore_stock(db, order)
    reason = (payload.reason if payload else None) or None
    if reason is not None:
        reason = reason.strip()[:500] or None
    order.cancel_reason = reason
    order = await order_service.update_status(db, order, "cancelled")
    return await _serialize(db, order, viewer=current_user)
