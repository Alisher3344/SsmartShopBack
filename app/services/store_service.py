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
