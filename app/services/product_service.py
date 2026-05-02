from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.review import Review
from app.schemas.product import ProductCreate, ProductUpdate


async def get_review_stats(db: AsyncSession, product_ids: list[int]) -> dict[int, tuple[int, float]]:
    """{product_id: (count, avg_rating)} — sharhlardan dinamik hisoblangan."""
    if not product_ids:
        return {}
    res = await db.execute(
        select(
            Review.product_id,
            func.count(Review.id),
            func.avg(Review.rating),
        )
        .where(Review.product_id.in_(product_ids))
        .group_by(Review.product_id)
    )
    return {pid: (int(cnt), float(avg or 0)) for pid, cnt, avg in res.all()}


def attach_stats(product: Product, stats: dict[int, tuple[int, float]]) -> Product:
    """ProductOut serializatsiyasi uchun reviewsCount/avgRating qo'shamiz."""
    cnt, avg = stats.get(product.id, (0, 0.0))
    product.reviews_count = cnt
    product.avg_rating = round(avg, 1) if cnt else 0.0
    return product


async def list_products(db: AsyncSession, store_id: int | None = None) -> list[Product]:
    q = select(Product).order_by(Product.id.desc())
    if store_id is not None:
        q = q.where(Product.store_id == store_id)
    result = await db.execute(q)
    items = list(result.scalars().all())
    stats = await get_review_stats(db, [p.id for p in items])
    return [attach_stats(p, stats) for p in items]


async def get_product(db: AsyncSession, product_id: int) -> Product | None:
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if product:
        stats = await get_review_stats(db, [product.id])
        attach_stats(product, stats)
    return product


async def create_product(db: AsyncSession, data: ProductCreate) -> Product:
    payload = data.model_dump(by_alias=False)
    payload["name"] = data.name.model_dump()
    payload["description"] = data.description.model_dump()
    product = Product(**payload)
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


async def update_product(db: AsyncSession, product: Product, data: ProductUpdate) -> Product:
    # Faqat aniq yuborilgan field'larni olamiz (exclude_unset)
    sent_fields = data.model_fields_set
    payload = data.model_dump(exclude_unset=True, by_alias=False)
    if "name" in payload and data.name is not None:
        payload["name"] = data.name.model_dump()
    if "description" in payload and data.description is not None:
        payload["description"] = data.description.model_dump()
    # store_id: agar field klient tomondan yuborilmagan bo'lsa — o'tkazib yuboramiz.
    # Yuborilgan bo'lsa (None ham) — qabul qilamiz (super admin orphan biriktirishi uchun).
    if "store_id" not in sent_fields and "storeId" not in sent_fields:
        payload.pop("store_id", None)
    for k, v in payload.items():
        setattr(product, k, v)
    await db.commit()
    await db.refresh(product)
    return product


async def delete_product(db: AsyncSession, product: Product) -> None:
    await db.delete(product)
    await db.commit()


async def toggle_sale(db: AsyncSession, product: Product) -> Product:
    product.on_sale = not product.on_sale
    await db.commit()
    await db.refresh(product)
    return product
