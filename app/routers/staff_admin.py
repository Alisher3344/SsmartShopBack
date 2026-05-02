from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_superadmin
from app.db.database import get_db
from app.schemas.user import StaffAdminCreate, StaffAdminUpdate, UserOut
from app.services import user_service

router = APIRouter(
    prefix="/staff",
    tags=["staff"],
    dependencies=[Depends(require_superadmin)],
)


@router.get("", response_model=list[UserOut])
async def list_admins(
    store_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    return await user_service.list_staff_admins(db, store_id=store_id)


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_admin(data: StaffAdminCreate, db: AsyncSession = Depends(get_db)):
    username = data.username.strip().lower()
    existing = await user_service.get_user_by_username(db, username)
    if existing:
        # Orphan/eski user (staff yoki eski admin sales_admin role'da) — qayta ulash.
        # Magazin o'chirilganda store_id ON DELETE SET NULL qilinadi.
        # Faqat boshqa hisob (faol pickup_admin/superadmin) bilan to'qnashganda 400.
        can_rebind = (
            existing.role in ("staff", "admin")
            and (existing.store_id is None or existing.store_id == data.store_id)
        )
        if can_rebind:
            existing.role = "staff"
            await db.commit()
            return await user_service.update_staff_admin(
                db, existing,
                password=data.password,
                full_name=data.full_name,
                phone=data.phone,
                store_id=data.store_id,
                is_active=True,
            )
        raise HTTPException(status_code=400, detail="Bu username band")
    return await user_service.create_staff_admin(
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
    data: StaffAdminUpdate,
    db: AsyncSession = Depends(get_db),
):
    admin = await user_service.get_staff_admin_by_id(db, user_id)
    if not admin:
        raise HTTPException(status_code=404, detail="Staff topilmadi")
    new_username = data.username.strip().lower() if data.username else None
    if new_username and new_username != admin.username:
        existing = await user_service.get_user_by_username(db, new_username)
        if existing and existing.id != admin.id:
            raise HTTPException(status_code=400, detail="Bu username band")
    return await user_service.update_staff_admin(
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
    admin = await user_service.get_staff_admin_by_id(db, user_id)
    if not admin:
        raise HTTPException(status_code=404, detail="Staff topilmadi")
    await user_service.delete_staff_admin(db, admin)
