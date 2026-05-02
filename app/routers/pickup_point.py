from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_pickup_admin, require_superadmin
from app.core.telegram_bot import notify_user_with_photos
from app.db.database import get_db
from app.models.user import User
from app.schemas.pickup_point import PickupPointCreate, PickupPointOut, PickupPointUpdate
from app.schemas.user import PickupAdminCreate, PickupAdminUpdate, UserOut
from app.services import order_service, pickup_point_service, user_service


def _format_ready_message(order, point_name: dict | None) -> str:
    """Punkt mahsulotni qabul qilgach foydalanuvchiga yuboriladigan xabar."""
    lines = ["📦 <b>Mahsulotingiz punktga yetib keldi!</b>", ""]
    for it in order.items:
        nm = (it.get("name") or {}).get("uz") or (it.get("name") or {}).get("ru") or "—"
        price = it.get("price", 0)
        qty = it.get("qty", 1)
        lines.append(f"• {nm} — {qty} × {price:,} so'm".replace(",", " "))
    lines.append("")
    lines.append(f"💰 Jami: <b>{order.total:,} so'm</b>".replace(",", " "))
    lines.append("")
    lines.append(f"🔢 Olib ketish kodingiz:\n<code>{order.pickup_code}</code>")
    if point_name:
        lines.append("")
        lines.append(f"📍 Punkt: {point_name.get('uz', '')}")
    lines.append("")
    lines.append("Punktga borib, ushbu kodni adminga ko'rsating.")
    return "\n".join(lines)


class PickupCodeIn(BaseModel):
    code: str = Field(min_length=8, max_length=8)


async def _serialize_order(db: AsyncSession, order) -> dict:
    from app.schemas.order import OrderOut
    p_name, p_addr = await order_service.get_pickup_point_info(db, order.pickup_point_id)
    out = OrderOut.model_validate(order).model_dump(by_alias=True)
    out["pickupPointName"] = p_name
    out["pickupPointAddress"] = p_addr
    return out

router = APIRouter(prefix="/pickup-points", tags=["pickup-points"])


@router.get("", response_model=list[PickupPointOut], response_model_by_alias=True)
async def list_points(
    only_active: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    return await pickup_point_service.list_points(db, only_active=only_active)


@router.get("/my", response_model=PickupPointOut, response_model_by_alias=True)
async def my_pickup_point(
    user: User = Depends(require_pickup_admin),
    db: AsyncSession = Depends(get_db),
):
    """Pickup admin o'z punktini olishi uchun."""
    point = await pickup_point_service.get_point(db, user.pickup_point_id)
    if not point:
        raise HTTPException(status_code=404, detail="Punkt topilmadi")
    return point


@router.get("/my/orders")
async def my_pickup_orders(
    status_filter: str | None = Query(None, alias="status"),
    user: User = Depends(require_pickup_admin),
    db: AsyncSession = Depends(get_db),
):
    """Pickup adminga tegishli punktdagi buyurtmalar."""
    orders = await order_service.list_orders_for_admin(
        db, pickup_point_id=user.pickup_point_id, status=status_filter
    )
    return [await _serialize_order(db, o) for o in orders]


@router.post("/my/receive")
async def receive_by_transit_code(
    data: PickupCodeIn,
    user: User = Depends(require_pickup_admin),
    db: AsyncSession = Depends(get_db),
):
    """Punkt admin mahsulot bilan kelgan 1-kodni (transit_code) kiritadi.
    Mahsulot ro'yxatga qo'shiladi va foydalanuvchiga 2-kod (pickup_code) yuboriladi."""
    code = data.code.strip()
    # Avval kod bo'yicha qidiramiz (punkt sharti bilan)
    order = await order_service.get_order_by_transit_code(db, code, user.pickup_point_id)
    if not order:
        # Punkt sharti yo'q holda ham qidiramiz - aniq sabab uchun
        any_order = await order_service.get_order_by_transit_code_any(db, code)
        if not any_order:
            raise HTTPException(status_code=404, detail="Bu kodli mahsulot tizimda yo'q")
        if any_order.pickup_point_id != user.pickup_point_id:
            raise HTTPException(
                status_code=403,
                detail="Bu mahsulot boshqa punktga yo'naltirilgan",
            )
        order = any_order

    if order.status == "ready" or order.status == "delivered":
        raise HTTPException(status_code=400, detail="Bu mahsulot allaqachon qabul qilingan")
    if order.status == "cancelled":
        raise HTTPException(status_code=400, detail="Bu buyurtma bekor qilingan")
    if order.status != "confirmed":
        raise HTTPException(status_code=400, detail="Mahsulot hali sotuv admin tomonidan tasdiqlanmagan")

    order = await order_service.receive_at_pickup(db, order)

    # Foydalanuvchiga 2-kodni Telegram orqali rasmlar bilan yuboramiz
    chat_id = await order_service.get_user_telegram_id(db, order.user_id)
    if chat_id:
        p_name, _ = await order_service.get_pickup_point_info(db, order.pickup_point_id)
        image_urls = [it.get("image") for it in (order.items or []) if it.get("image")]
        await notify_user_with_photos(
            chat_id, image_urls, _format_ready_message(order, p_name)
        )

    return await _serialize_order(db, order)


@router.post("/my/lookup")
async def lookup_by_pickup_code(
    data: PickupCodeIn,
    user: User = Depends(require_pickup_admin),
    db: AsyncSession = Depends(get_db),
):
    """Mijoz aytgan 2-kod (pickup_code) bo'yicha buyurtmani topib qaytaradi.
    Status o'zgarmaydi — admin avval ma'lumotlarni ko'radi va keyin tasdiqlash/qaytarish tanlaydi."""
    code = data.code.strip()
    order = await order_service.get_order_by_pickup_code(db, code, user.pickup_point_id)
    if not order:
        raise HTTPException(status_code=404, detail="Bunday kodli buyurtma topilmadi")
    if order.status == "delivered":
        raise HTTPException(status_code=400, detail="Bu buyurtma allaqachon topshirilgan")
    if order.status != "ready":
        raise HTTPException(status_code=400, detail="Buyurtma hali tayyor emas")
    return await _serialize_order(db, order)


@router.post("/my/deliver")
async def deliver_by_code(
    data: PickupCodeIn,
    user: User = Depends(require_pickup_admin),
    db: AsyncSession = Depends(get_db),
):
    """Punkt admin 2-kodni tasdiqladi -> mahsulot mijozga topshirildi (delivered)."""
    code = data.code.strip()
    order = await order_service.get_order_by_pickup_code(db, code, user.pickup_point_id)
    if not order:
        raise HTTPException(status_code=404, detail="Bunday kodli buyurtma topilmadi")
    if order.status == "delivered":
        raise HTTPException(status_code=400, detail="Bu buyurtma allaqachon topshirilgan")
    if order.status != "ready":
        raise HTTPException(status_code=400, detail="Buyurtma hali tayyor emas")
    order = await order_service.mark_delivered(db, order)
    return await _serialize_order(db, order)


@router.post(
    "",
    response_model=PickupPointOut,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_superadmin)],
)
async def create_point(data: PickupPointCreate, db: AsyncSession = Depends(get_db)):
    return await pickup_point_service.create_point(db, data)


@router.put(
    "/{point_id}",
    response_model=PickupPointOut,
    response_model_by_alias=True,
    dependencies=[Depends(require_superadmin)],
)
async def update_point(point_id: int, data: PickupPointUpdate, db: AsyncSession = Depends(get_db)):
    point = await pickup_point_service.get_point(db, point_id)
    if not point:
        raise HTTPException(status_code=404, detail="Pickup point not found")
    return await pickup_point_service.update_point(db, point, data)


@router.delete(
    "/{point_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_superadmin)],
)
async def delete_point(point_id: int, db: AsyncSession = Depends(get_db)):
    point = await pickup_point_service.get_point(db, point_id)
    if not point:
        raise HTTPException(status_code=404, detail="Pickup point not found")
    await pickup_point_service.delete_point(db, point)


# ===== Pickup point adminlar (ko'pchilik bo'lishi mumkin) =====

@router.get(
    "/{point_id}/admins",
    response_model=list[UserOut],
    dependencies=[Depends(require_superadmin)],
)
async def list_point_admins(point_id: int, db: AsyncSession = Depends(get_db)):
    point = await pickup_point_service.get_point(db, point_id)
    if not point:
        raise HTTPException(status_code=404, detail="Pickup point not found")
    return await user_service.list_pickup_admins(db, point_id)


@router.post(
    "/{point_id}/admins",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_superadmin)],
)
async def create_point_admin(
    point_id: int,
    data: PickupAdminCreate,
    db: AsyncSession = Depends(get_db),
):
    point = await pickup_point_service.get_point(db, point_id)
    if not point:
        raise HTTPException(status_code=404, detail="Pickup point not found")
    username = data.username.strip().lower()
    if await user_service.get_user_by_username(db, username):
        raise HTTPException(status_code=400, detail="Bu username band")
    return await user_service.create_pickup_admin(
        db,
        pickup_point_id=point_id,
        username=username,
        password=data.password,
        full_name=data.full_name,
        phone=data.phone,
    )


@router.put(
    "/admins/{user_id}",
    response_model=UserOut,
    dependencies=[Depends(require_superadmin)],
)
async def update_point_admin(
    user_id: int,
    data: PickupAdminUpdate,
    db: AsyncSession = Depends(get_db),
):
    admin = await user_service.get_pickup_admin_by_id(db, user_id)
    if not admin:
        raise HTTPException(status_code=404, detail="Admin topilmadi")
    new_username = data.username.strip().lower() if data.username else None
    if new_username and new_username != admin.username:
        existing = await user_service.get_user_by_username(db, new_username)
        if existing and existing.id != admin.id:
            raise HTTPException(status_code=400, detail="Bu username band")
    return await user_service.update_pickup_admin(
        db,
        admin,
        username=new_username,
        password=data.password,
        full_name=data.full_name,
        phone=data.phone,
        is_active=data.is_active,
    )


@router.delete(
    "/admins/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_superadmin)],
)
async def delete_point_admin(user_id: int, db: AsyncSession = Depends(get_db)):
    admin = await user_service.get_pickup_admin_by_id(db, user_id)
    if not admin:
        raise HTTPException(status_code=404, detail="Admin topilmadi")
    await user_service.delete_pickup_admin(db, admin)
