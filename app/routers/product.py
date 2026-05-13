from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_admin
from app.db.database import get_db
from app.models.user import User
from app.schemas.product import ProductCreate, ProductOut, ProductUpdate
from app.services import product_service, store_service

router = APIRouter(prefix="/products", tags=["products"])


async def _ensure_store_access(db: AsyncSession, user: User, store_id: int | None):
    """Mahsulotga ruxsat tekshiruvi:
       - superadmin: barchasiga
       - admin (sotuv admin): faqat asosiy magazin (is_main) mahsulotlariga
       - staff (magazin admin): faqat o'z magazinining mahsulotlariga
    """
    if user.role == "superadmin":
        return
    if user.role == "admin":
        main_id = await store_service.get_main_store_id(db)
        if store_id != main_id:
            raise HTTPException(
                status_code=403,
                detail="Bu mahsulot boshqa magazinga tegishli",
            )
        return
    # staff
    if user.store_id is None:
        raise HTTPException(
            status_code=403,
            detail="Sizga magazin biriktirilmagan, super admin bilan bog'laning",
        )
    if store_id != user.store_id:
        raise HTTPException(status_code=403, detail="Bu mahsulot boshqa magazinga tegishli")


@router.get("", response_model=list[ProductOut], response_model_by_alias=True)
async def list_products(
    store_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Public: barcha mahsulotlar yoki store_id bo'yicha."""
    return await product_service.list_products(db, store_id=store_id)


@router.get("/my", response_model=list[ProductOut], response_model_by_alias=True)
async def my_products(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin/sotuv admin: asosiy magazin mahsulotlari. Staff: o'z magazini. Super admin: barchasi."""
    if user.role == "superadmin":
        return await product_service.list_products(db)
    if user.role == "admin":
        main_id = await store_service.get_main_store_id(db)
        if main_id is None:
            return []
        return await product_service.list_products(db, store_id=main_id)
    # staff
    if user.store_id is None:
        return []
    return await product_service.list_products(db, store_id=user.store_id)


@router.get("/{product_id}", response_model=ProductOut, response_model_by_alias=True)
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    product = await product_service.get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.post(
    "",
    response_model=ProductOut,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
async def create_product(
    data: ProductCreate,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    # Staff: store_id avto-belgilanadi (o'z magazini).
    # Admin (sotuv admin): har doim asosiy magazin.
    # Super admin: formada tanlash, tanlanmasa asosiy magazin.
    if user.role == "staff":
        if user.store_id is None:
            raise HTTPException(
                status_code=403,
                detail="Sizga magazin biriktirilmagan, super admin bilan bog'laning",
            )
        data.store_id = user.store_id
    elif user.role == "admin":
        main_id = await store_service.get_main_store_id(db)
        if main_id is None:
            raise HTTPException(status_code=500, detail="Asosiy magazin sozlanmagan")
        data.store_id = main_id
    else:  # superadmin
        if data.store_id is None:
            data.store_id = await store_service.get_main_store_id(db)
    return await product_service.create_product(db, data)


@router.put(
    "/{product_id}",
    response_model=ProductOut,
    response_model_by_alias=True,
)
async def update_product(
    product_id: int,
    data: ProductUpdate,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    product = await product_service.get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    await _ensure_store_access(db, user, product.store_id)
    # Staff va sotuv admin store_id'ni o'zgartira olmaydi — service None'ni skip qiladi
    if user.role in ("staff", "admin"):
        data.store_id = None
    return await product_service.update_product(db, product, data)


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_product(
    product_id: int,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    product = await product_service.get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    await _ensure_store_access(db, user, product.store_id)
    await product_service.delete_product(db, product)


@router.post(
    "/{product_id}/toggle-sale",
    response_model=ProductOut,
    response_model_by_alias=True,
)
async def toggle_sale(
    product_id: int,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    product = await product_service.get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    await _ensure_store_access(db, user, product.store_id)
    return await product_service.toggle_sale(db, product)
