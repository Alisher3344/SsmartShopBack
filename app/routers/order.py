from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ADMIN_ROLES, get_current_user, require_admin
from app.db.database import get_db
from app.models.user import User
from app.schemas.order import CancelOrderIn, OrderCreate, OrderOut
from app.services import order_service

router = APIRouter(prefix="/orders", tags=["orders"])


async def _serialize(db: AsyncSession, order, viewer: User | None = None) -> dict:
    p_name, p_addr = await order_service.get_pickup_point_info(db, order.pickup_point_id)
    out = OrderOut.model_validate(order).model_dump(by_alias=True)
    out["pickupPointName"] = p_name
    out["pickupPointAddress"] = p_addr

    # Admin viewer uchun — customer MyID tasdiqlangan vaqti (badge ko'rsatish uchun).
    # Oddiy user o'z buyurtmasiga qarayotganda bu kerak emas.
    if viewer is not None and viewer.role in ADMIN_ROLES:
        customer = await db.get(User, order.user_id)
        out["customerMyidVerifiedAt"] = (
            customer.myid_verified_at.isoformat()
            if customer and customer.myid_verified_at
            else None
        )

    # transit_code'ni admin rollarga scope bo'yicha ko'rsatamiz, qolganlarga yashiramiz.
    if viewer is not None and order.transit_code:
        if viewer.role in ADMIN_ROLES:
            scope = await order_service.resolve_order_scope(db, viewer)
            if not scope.can_see_transit(order.store_id):
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
    """Buyurtmalar ro'yxati. Scope role bo'yicha: superadmin barchasi,
    staff/admin — o'z magazini buyurtmalari."""
    scope = await order_service.resolve_order_scope(db, user)
    # admin/staff bo'lib magazin ulanmagan bo'lsa, bo'sh ro'yxat
    if user.role in ("staff", "admin") and scope.store_id is None:
        return []
    orders = await order_service.list_orders_for_admin(
        db,
        pickup_point_id=pickup_point_id,
        status=status_filter,
        store_id=scope.store_id,
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
    scope = await order_service.resolve_order_scope(db, user)
    if not scope.can_manage(order.store_id):
        raise HTTPException(status_code=403, detail="Bu buyurtma boshqa magazinga tegishli")
    if order.status != "pending":
        raise HTTPException(status_code=400, detail="Faqat kutilayotgan buyurtmalarni tasdiqlash mumkin")
    order = await order_service.confirm_with_transit_code(db, order)
    return await _serialize(db, order, viewer=user)


@router.post("/{order_id}/dispatch")
async def dispatch_order(
    order_id: int,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin mahsulot kodini (yorliq) chop etib punktga jo'natdi — doimiy belgi.
    Status o'zgarmaydi (confirmed); UI kartochkani 'hira' qiladi, ikkinchi admin
    qayta qabul qilmasligi uchun."""
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
    scope = await order_service.resolve_order_scope(db, user)
    if not scope.can_manage(order.store_id):
        raise HTTPException(status_code=403, detail="Bu buyurtma boshqa magazinga tegishli")
    if order.status != "confirmed" or not order.transit_code:
        raise HTTPException(
            status_code=400,
            detail="Faqat tasdiqlangan (kod berilgan) buyurtmani jo'natish mumkin",
        )
    order = await order_service.mark_dispatched(db, order, user)
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
    is_owner = order.user_id == current_user.id
    can_admin_manage = (
        current_user.role in ADMIN_ROLES
        and (await order_service.resolve_order_scope(db, current_user)).can_manage(order.store_id)
    )
    if not (is_owner or can_admin_manage):
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
