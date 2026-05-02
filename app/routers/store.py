from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_superadmin
from app.db.database import get_db
from app.schemas.store import StoreCreate, StoreOut, StoreUpdate
from app.services import store_service

router = APIRouter(prefix="/stores", tags=["stores"])


@router.get("", response_model=list[StoreOut])
async def list_stores(only_active: bool = Query(False), db: AsyncSession = Depends(get_db)):
    """Magazinlar ro'yxati — public (foydalanuvchi ham filterlash uchun)."""
    return await store_service.list_stores(db, only_active=only_active)


@router.post("", response_model=StoreOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_superadmin)])
async def create_store(data: StoreCreate, db: AsyncSession = Depends(get_db)):
    return await store_service.create_store(db, data)


@router.put("/{store_id}", response_model=StoreOut, dependencies=[Depends(require_superadmin)])
async def update_store(store_id: int, data: StoreUpdate, db: AsyncSession = Depends(get_db)):
    store = await store_service.get_store(db, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Magazin topilmadi")
    return await store_service.update_store(db, store, data)


@router.delete("/{store_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_superadmin)])
async def delete_store(store_id: int, db: AsyncSession = Depends(get_db)):
    store = await store_service.get_store(db, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Magazin topilmadi")
    await store_service.delete_store(db, store)
