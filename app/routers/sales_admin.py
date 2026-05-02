from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_superadmin
from app.db.database import get_db
from app.schemas.user import SalesAdminCreate, SalesAdminUpdate, UserOut
from app.services import user_service

router = APIRouter(
    prefix="/sales-admins",
    tags=["sales-admins"],
    dependencies=[Depends(require_superadmin)],
)


@router.get("", response_model=list[UserOut])
async def list_admins(db: AsyncSession = Depends(get_db)):
    return await user_service.list_sales_admins(db)


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_admin(data: SalesAdminCreate, db: AsyncSession = Depends(get_db)):
    username = data.username.strip().lower()
    if await user_service.get_user_by_username(db, username):
        raise HTTPException(status_code=400, detail="Bu username band")
    return await user_service.create_sales_admin(
        db,
        username=username,
        password=data.password,
        full_name=data.full_name,
        phone=data.phone,
        store_id=data.store_id,
    )


@router.put("/{user_id}", response_model=UserOut)
async def update_admin(
    user_id: int,
    data: SalesAdminUpdate,
    db: AsyncSession = Depends(get_db),
):
    admin = await user_service.get_sales_admin_by_id(db, user_id)
    if not admin:
        raise HTTPException(status_code=404, detail="Admin topilmadi")
    new_username = data.username.strip().lower() if data.username else None
    if new_username and new_username != admin.username:
        existing = await user_service.get_user_by_username(db, new_username)
        if existing and existing.id != admin.id:
            raise HTTPException(status_code=400, detail="Bu username band")
    return await user_service.update_sales_admin(
        db,
        admin,
        username=new_username,
        password=data.password,
        full_name=data.full_name,
        phone=data.phone,
        is_active=data.is_active,
        store_id=data.store_id,
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin(user_id: int, db: AsyncSession = Depends(get_db)):
    admin = await user_service.get_sales_admin_by_id(db, user_id)
    if not admin:
        raise HTTPException(status_code=404, detail="Admin topilmadi")
    await user_service.delete_sales_admin(db, admin)
