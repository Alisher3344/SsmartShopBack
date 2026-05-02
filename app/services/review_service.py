from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order
from app.models.product import Product
from app.models.review import Review
from app.models.user import User
from app.schemas.review import ReviewCreate


async def list_pending_for_user(db: AsyncSession, user_id: int) -> list[dict]:
    """Foydalanuvchining yetkazilgan buyurtmalaridagi mahsulotlar.
    Faqat sharh yozilmaganlari qaytariladi.
    Har (product_id, order_id) bo'yicha unique."""
    res = await db.execute(
        select(Order)
        .where(Order.user_id == user_id, Order.status == "delivered")
        .order_by(Order.delivered_at.desc().nullslast(), Order.id.desc())
    )
    orders = list(res.scalars().all())

    # Foydalanuvchi yozgan sharhlar — qaysi product_id'larni "qoplagan"
    rev_res = await db.execute(
        select(Review.product_id).where(Review.user_id == user_id)
    )
    reviewed_product_ids = {row[0] for row in rev_res.all()}

    # Mahsulot id -> name/image (barchasini bir so'rov bilan)
    all_pids = []
    for o in orders:
        for it in (o.items or []):
            pid = it.get("product_id")
            if pid:
                all_pids.append(pid)
    products: dict[int, Product] = {}
    if all_pids:
        p_res = await db.execute(select(Product).where(Product.id.in_(all_pids)))
        products = {p.id: p for p in p_res.scalars().all()}

    seen: set[int] = set()
    result: list[dict] = []
    for o in orders:
        for it in (o.items or []):
            pid = it.get("product_id")
            if not pid or pid in seen or pid in reviewed_product_ids:
                continue
            seen.add(pid)
            product = products.get(pid)
            name = product.name if product else (it.get("name") or {})
            image = product.image if product else (it.get("image") or "")
            result.append({
                "productId": pid,
                "orderId": o.id,
                "name": name,
                "image": image,
                "deliveredAt": o.delivered_at,
            })
    return result


async def list_my_reviews(db: AsyncSession, user_id: int) -> list[dict]:
    res = await db.execute(
        select(Review).where(Review.user_id == user_id).order_by(Review.created_at.desc())
    )
    reviews = list(res.scalars().all())
    pids = list({r.product_id for r in reviews})
    products: dict[int, Product] = {}
    if pids:
        p_res = await db.execute(select(Product).where(Product.id.in_(pids)))
        products = {p.id: p for p in p_res.scalars().all()}
    out = []
    for r in reviews:
        prod = products.get(r.product_id)
        out.append({
            "id": r.id,
            "userId": r.user_id,
            "productId": r.product_id,
            "orderId": r.order_id,
            "rating": r.rating,
            "text": r.text,
            "createdAt": r.created_at,
            "productName": prod.name if prod else None,
            "productImage": prod.image if prod else None,
        })
    return out


async def list_product_reviews(db: AsyncSession, product_id: int) -> list[dict]:
    res = await db.execute(
        select(Review, User.full_name, User.username)
        .join(User, User.id == Review.user_id)
        .where(Review.product_id == product_id)
        .order_by(Review.created_at.desc())
    )
    rows = res.all()
    return [
        {
            "id": r.id,
            "userId": r.user_id,
            "productId": r.product_id,
            "orderId": r.order_id,
            "rating": r.rating,
            "text": r.text,
            "createdAt": r.created_at,
            "userName": full_name or username or "Anonim",
        }
        for r, full_name, username in rows
    ]


async def get_existing_review(
    db: AsyncSession, user_id: int, product_id: int
) -> Review | None:
    res = await db.execute(
        select(Review).where(
            Review.user_id == user_id, Review.product_id == product_id
        )
    )
    return res.scalar_one_or_none()


async def create_review(
    db: AsyncSession, user: User, data: ReviewCreate
) -> Review:
    # Tekshirish: foydalanuvchi shu mahsulotni delivered statusda olganmi?
    res = await db.execute(
        select(Order).where(
            Order.user_id == user.id, Order.status == "delivered"
        )
    )
    has_delivered = False
    for o in res.scalars().all():
        for it in (o.items or []):
            if it.get("product_id") == data.product_id:
                has_delivered = True
                break
        if has_delivered:
            break
    if not has_delivered:
        raise ValueError("Bu mahsulotni hali sotib olmagansiz yoki olib ketmagansiz")

    if await get_existing_review(db, user.id, data.product_id):
        raise ValueError("Bu mahsulotga allaqachon sharh yozgansiz")

    review = Review(
        user_id=user.id,
        product_id=data.product_id,
        order_id=data.order_id,
        rating=data.rating,
        text=(data.text or "").strip() or None,
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)
    return review
