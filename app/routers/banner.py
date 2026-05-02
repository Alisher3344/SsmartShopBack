from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_superadmin
from app.db.database import get_db
from app.schemas.banner import BannerCreate, BannerOut, BannerUpdate
from app.services import banner_service

router = APIRouter(prefix="/banners", tags=["banners"])


@router.get("", response_model=list[BannerOut], response_model_by_alias=True)
async def list_banners(db: AsyncSession = Depends(get_db)):
    return await banner_service.list_banners(db)


@router.post(
    "",
    response_model=BannerOut,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_superadmin)],
)
async def create_banner(data: BannerCreate, db: AsyncSession = Depends(get_db)):
    return await banner_service.create_banner(db, data)


@router.put(
    "/{banner_id}",
    response_model=BannerOut,
    response_model_by_alias=True,
    dependencies=[Depends(require_superadmin)],
)
async def update_banner(banner_id: int, data: BannerUpdate, db: AsyncSession = Depends(get_db)):
    banner = await banner_service.get_banner(db, banner_id)
    if not banner:
        raise HTTPException(status_code=404, detail="Banner not found")
    return await banner_service.update_banner(db, banner, data)


@router.delete(
    "/{banner_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_superadmin)],
)
async def delete_banner(banner_id: int, db: AsyncSession = Depends(get_db)):
    banner = await banner_service.get_banner(db, banner_id)
    if not banner:
        raise HTTPException(status_code=404, detail="Banner not found")
    await banner_service.delete_banner(db, banner)


@router.post(
    "/{banner_id}/toggle-active",
    response_model=BannerOut,
    response_model_by_alias=True,
    dependencies=[Depends(require_superadmin)],
)
async def toggle_active(banner_id: int, db: AsyncSession = Depends(get_db)):
    banner = await banner_service.get_banner(db, banner_id)
    if not banner:
        raise HTTPException(status_code=404, detail="Banner not found")
    return await banner_service.toggle_active(db, banner)
