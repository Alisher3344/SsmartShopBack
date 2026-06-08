import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order
from app.models.pickup_point import PickupPoint
from app.models.product import Product
from app.models.user import User
from app.schemas.order import OrderCreate
from app.services import store_service

CANCELLED_TTL_HOURS = 24


@dataclass(frozen=True)
class OrderScope:
    """Buyurtmalar uchun data-scope.

    `store_id` None bo'lsa — barcha buyurtmalarni ko'radi (superadmin).
    Aks holda faqat shu magazin buyurtmalari ko'rinadi.
    """
    store_id: int | None
    role: str

    def can_see_transit(self, order_store_id: int | None) -> bool:
        if self.store_id is None:
            return True
        return order_store_id == self.store_id

    def can_manage(self, order_store_id: int | None) -> bool:
        if self.role == "superadmin":
            return True
        if self.role == "staff":
            return order_store_id == self.store_id
        if self.role == "admin":
            return order_store_id == self.store_id
        return False


async def resolve_order_scope(db: AsyncSession, user: User) -> OrderScope:
    """Foydalanuvchining buyurtmalarga ruxsat scope'i. Faqat admin rollarda chaqiriladi."""
    if user.role == "superadmin":
        return OrderScope(store_id=None, role="superadmin")
    if user.role == "staff":
        return OrderScope(store_id=user.store_id, role="staff")
    if user.role == "admin":
        main_id = await store_service.get_main_store_id(db)
        return OrderScope(store_id=main_id, role="admin")
    return OrderScope(store_id=None, role=user.role)


async def cleanup_expired_cancelled(db: AsyncSession) -> int:
    """1 kundan oshgan bekor qilingan buyurtmalarni o'chirish."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=CANCELLED_TTL_HOURS)
    result = await db.execute(
        delete(Order).where(Order.status == "cancelled", Order.updated_at < cutoff)
    )
    await db.commit()
    return result.rowcount or 0


async def create_order(db: AsyncSession, user: User, data: OrderCreate) -> Order:
    if not data.items:
        raise ValueError("Buyurtma bo'sh bo'lishi mumkin emas")

    product_ids = [item.product_id for item in data.items]
    res = await db.execute(select(Product).where(Product.id.in_(product_ids)))
    products = {p.id: p for p in res.scalars().all()}

    items_snapshot = []
    total = 0
    store_id_from_items: int | None = None
    for it in data.items:
        product = products.get(it.product_id)
        if not product:
            raise ValueError(f"Mahsulot topilmadi: id={it.product_id}")
        if product.stock < it.qty:
            raise ValueError(
                f"\"{product.name.get('uz', '?')}\" zaxirasida faqat {product.stock} dona qoldi"
            )
        items_snapshot.append({
            "product_id": product.id,
            "name": product.name,
            "qty": it.qty,
            "price": product.price,
            "image": product.image or "",
            "store_id": product.store_id,
        })
        total += product.price * it.qty
        # Birinchi mahsulot store_id'sini orderga yozamiz (asosiy magazin)
        if store_id_from_items is None and product.store_id is not None:
            store_id_from_items = product.store_id

    if data.delivery_type == "pickup" and not data.pickup_point_id:
        raise ValueError("Pickup tanlanganda punkt majburiy")
    if data.delivery_type == "courier":
        total += 25000  # yetkazib berish narxi
        if not data.delivery_address:
            raise ValueError("Manzil majburiy")

    # Stock'ni kamaytiramiz (buyurtma reserve qilingan deb hisoblanadi)
    for it in data.items:
        products[it.product_id].stock -= it.qty

    # Online to'lov (card) yoki rassrochka (instalment) — tasdiqlash kelguncha
    # transit_code generatsiya qilmaymiz. Cash — eski avto-tasdiqlash oqimi.
    is_deferred_payment = data.payment_method in ("card", "instalment")
    initial_status = "pending_payment" if is_deferred_payment else "confirmed"
    transit_code = (
        None if is_deferred_payment else await _generate_unique_code(db, Order.transit_code)
    )

    order = Order(
        user_id=user.id,
        pickup_point_id=data.pickup_point_id if data.delivery_type == "pickup" else None,
        store_id=store_id_from_items,
        delivery_type=data.delivery_type,
        delivery_address=data.delivery_address if data.delivery_type == "courier" else None,
        payment_method=data.payment_method,
        items=items_snapshot,
        total=total,
        comment=data.comment,
        customer_name=user.full_name,
        customer_phone=user.phone,
        status=initial_status,
        payment_status="pending",
        transit_code=transit_code,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


async def finalize_after_payment(db: AsyncSession, order: Order) -> Order:
    """To'lov muvaffaqiyatli yakunlangach buyurtmani 'confirmed' ga o'tkazib,
    transit_code generatsiya qilamiz (idempotent)."""
    changed = False
    if order.status == "pending_payment":
        order.status = "confirmed"
        changed = True
    if order.payment_status != "paid":
        order.payment_status = "paid"
        changed = True
    if not order.transit_code:
        order.transit_code = await generate_transit_code(db)
        changed = True
    if changed:
        order.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(order)
    return order


async def mark_payment_failed(db: AsyncSession, order: Order) -> Order:
    """To'lov muvaffaqiyatsiz — order pending_payment'da qoladi, payment_status=failed."""
    if order.payment_status != "failed":
        order.payment_status = "failed"
        order.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(order)
    return order


async def restore_stock(db: AsyncSession, order: Order) -> None:
    """Bekor qilingan buyurtmaning stock'ini qaytaradi."""
    for it in order.items or []:
        pid = it.get("product_id")
        qty = it.get("qty", 0)
        if not pid or not qty:
            continue
        res = await db.execute(select(Product).where(Product.id == pid))
        product = res.scalar_one_or_none()
        if product:
            product.stock += qty
    await db.commit()


async def list_user_orders(db: AsyncSession, user_id: int) -> list[Order]:
    await cleanup_expired_cancelled(db)
    res = await db.execute(
        select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc())
    )
    return list(res.scalars().all())


async def list_orders_for_admin(
    db: AsyncSession,
    pickup_point_id: int | None = None,
    status: str | None = None,
    store_id: int | None = None,
    only_no_store: bool = False,
) -> list[Order]:
    await cleanup_expired_cancelled(db)
    q = select(Order)
    if pickup_point_id is not None:
        q = q.where(Order.pickup_point_id == pickup_point_id)
    if status:
        q = q.where(Order.status == status)
    if store_id is not None:
        q = q.where(Order.store_id == store_id)
    if only_no_store:
        q = q.where(Order.store_id.is_(None))
    q = q.order_by(Order.created_at.desc())
    res = await db.execute(q)
    return list(res.scalars().all())


async def get_order(db: AsyncSession, order_id: int) -> Order | None:
    res = await db.execute(select(Order).where(Order.id == order_id))
    return res.scalar_one_or_none()


async def update_status(db: AsyncSession, order: Order, status: str) -> Order:
    order.status = status
    order.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(order)
    return order


async def _generate_unique_code(db: AsyncSession, column) -> str:
    """8 xonali noyob kod (berilgan ustun bo'yicha unique tekshiriladi)."""
    for _ in range(30):
        code = "".join(secrets.choice("0123456789") for _ in range(8))
        exists = await db.execute(select(Order.id).where(column == code).limit(1))
        if exists.scalar_one_or_none() is None:
            return code
    raise RuntimeError("Noyob kod yaratib bo'lmadi")


async def generate_transit_code(db: AsyncSession) -> str:
    return await _generate_unique_code(db, Order.transit_code)


async def generate_pickup_code(db: AsyncSession) -> str:
    return await _generate_unique_code(db, Order.pickup_code)


async def confirm_with_transit_code(db: AsyncSession, order: Order) -> Order:
    """Sotuv admin tasdiqladi -> 1-kod (transit_code), status=confirmed.
    Foydalanuvchi bu kodni KO'RMAYDI — kod faqat sotuv adminga ko'rinadi."""
    if not order.transit_code:
        order.transit_code = await generate_transit_code(db)
    order.status = "confirmed"
    order.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(order)
    return order


async def mark_dispatched(db: AsyncSession, order: Order, user: User) -> Order:
    """Admin mahsulot kodini (yorliq) chop etib punktga jo'natdi.

    Idempotent: birinchi jo'natuvchi saqlanadi, qayta chaqirilsa o'zgarmaydi —
    shunda ikkinchi admin "qayta chop etsa" ham asl jo'natuvchi yozuvi qoladi."""
    if order.dispatched_at is None:
        now = datetime.now(timezone.utc)
        order.dispatched_at = now
        order.dispatched_by_id = user.id
        order.dispatched_by_name = user.full_name
        order.updated_at = now
        await db.commit()
        await db.refresh(order)
    return order


async def get_order_by_transit_code(
    db: AsyncSession, code: str, pickup_point_id: int
) -> Order | None:
    """Punkt admini 1-kodni qabul qilish uchun ishlatadi."""
    res = await db.execute(
        select(Order).where(
            Order.transit_code == code,
            Order.pickup_point_id == pickup_point_id,
        )
    )
    return res.scalar_one_or_none()


async def get_order_by_transit_code_any(db: AsyncSession, code: str) -> Order | None:
    """Punkt cheklovsiz — diagnostika uchun."""
    res = await db.execute(select(Order).where(Order.transit_code == code))
    return res.scalar_one_or_none()


async def receive_at_pickup(db: AsyncSession, order: Order) -> Order:
    """Punkt admini 1-kodni qabul qildi -> 2-kod (pickup_code) generatsiya, status=ready."""
    if not order.pickup_code:
        order.pickup_code = await generate_pickup_code(db)
    now = datetime.now(timezone.utc)
    order.status = "ready"
    order.received_at = now
    order.updated_at = now
    await db.commit()
    await db.refresh(order)
    return order


async def get_order_by_pickup_code(
    db: AsyncSession, code: str, pickup_point_id: int
) -> Order | None:
    """Punkt admini foydalanuvchidan kelgan 2-kodni topshirish uchun ishlatadi."""
    res = await db.execute(
        select(Order).where(
            Order.pickup_code == code,
            Order.pickup_point_id == pickup_point_id,
        )
    )
    return res.scalar_one_or_none()


async def mark_delivered(db: AsyncSession, order: Order) -> Order:
    now = datetime.now(timezone.utc)
    order.status = "delivered"
    order.delivered_at = now
    order.updated_at = now
    await db.commit()
    await db.refresh(order)
    return order


async def get_user_phone(db: AsyncSession, user_id: int) -> str | None:
    res = await db.execute(select(User.phone).where(User.id == user_id))
    return res.scalar_one_or_none()


async def get_pickup_point_info(db: AsyncSession, point_id: int | None):
    if not point_id:
        return None, None
    res = await db.execute(select(PickupPoint).where(PickupPoint.id == point_id))
    p = res.scalar_one_or_none()
    if not p:
        return None, None
    return p.name, p.address
