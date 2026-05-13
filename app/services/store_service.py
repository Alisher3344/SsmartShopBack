from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.store import Store
from app.schemas.store import StoreCreate, StoreUpdate


async def list_stores(db: AsyncSession, only_active: bool = False) -> list[Store]:
    q = select(Store).order_by(Store.id.asc())
    if only_active:
        q = q.where(Store.active.is_(True))
    res = await db.execute(q)
    return list(res.scalars().all())


async def get_store(db: AsyncSession, store_id: int) -> Store | None:
    res = await db.execute(select(Store).where(Store.id == store_id))
    return res.scalar_one_or_none()


async def get_main_store(db: AsyncSession) -> Store | None:
    """Asosiy magazin (is_main=true). Yo'q bo'lsa None."""
    res = await db.execute(select(Store).where(Store.is_main.is_(True)).limit(1))
    return res.scalar_one_or_none()


async def get_main_store_id(db: AsyncSession) -> int | None:
    store = await get_main_store(db)
    return store.id if store else None


async def create_store(db: AsyncSession, data: StoreCreate) -> Store:
    store = Store(**data.model_dump())
    db.add(store)
    await db.commit()
    await db.refresh(store)
    return store


async def update_store(db: AsyncSession, store: Store, data: StoreUpdate) -> Store:
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(store, k, v)
    await db.commit()
    await db.refresh(store)
    return store


async def delete_store(db: AsyncSession, store: Store) -> None:
    await db.delete(store)
    await db.commit()
