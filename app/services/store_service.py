from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.store import Store
from app.models.user import User
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


async def ensure_store_access(db: AsyncSession, user: User, store_id: int | None) -> None:
    """Magazinga tegishli resursga ruxsat tekshiruvi:
       - superadmin: barchasiga
       - admin (sotuv): faqat asosiy magazin (is_main=true)
       - staff: faqat o'z magazini

    Boshqa rollar 403 oladi.
    """
    if user.role == "superadmin":
        return
    if user.role == "admin":
        main_id = await get_main_store_id(db)
        if store_id != main_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu resurs boshqa magazinga tegishli",
            )
        return
    if user.role == "staff":
        if user.store_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Sizga magazin biriktirilmagan, super admin bilan bog'laning",
            )
        if store_id != user.store_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu resurs boshqa magazinga tegishli",
            )
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Ruxsat yo'q")


async def resolve_store_filter(db: AsyncSession, user: User) -> int | None:
    """Foydalanuvchining ko'rishi mumkin bo'lgan store_id (None = barchasi).

    Bu data-scope: "kim qaysi magazin resurslarini ko'radi". RBAC qatlami
    "kim umuman kira oladi" qarorini oladi (require_admin), bu funksiya esa
    natija qaysi magazindan kelishini cheklaydi.
    """
    if user.role == "superadmin":
        return None
    if user.role == "admin":
        return await get_main_store_id(db)
    if user.role == "staff":
        return user.store_id
    return None
