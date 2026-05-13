"""Flutter APK (mobil) uchun shop-only API.

Bu router faqat oddiy foydalanuvchi (shop user) uchun zarur bo'lgan endpointlarni
o'z ichiga oladi: auth, profil, katalog, buyurtmalar, sharhlar.

Admin, super admin, sotuv admin, punkt admin endpointlari bu yerga kirmaydi —
ular `/api/...` (boshqa router'lar)da qoldi.

Barcha endpointlar `/api/mobile/...` prefiksi bilan ochiqlanadi.
Autentifikatsiya: `Authorization: Bearer <jwt>` (foydalanuvchi tokeni).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_admin  # noqa: F401  (unused now, kept for parity)
from app.db.database import get_db
from app.models.banner import Banner
from app.models.store import Store
from app.models.user import User
from app.routers.user import get_current_user
from app.schemas.banner import BannerOut
from app.schemas.order import OrderCreate, OrderOut
from app.schemas.product import ProductOut
from app.schemas.review import PendingReviewItem, ReviewCreate, ReviewOut
from app.schemas.store import StoreOut
from app.schemas.user import ProfileUpdate, Token, UserOut
from app.routers.sms_otp import (
    CompleteRegisterPayload,
    PhoneLoginPayload,
    RequestPayload as PhonePayload,
    ResetCompletePayload,
    ResetVerifyOut,
    VerifyOut,
    VerifyPayload as OtpVerifyPayload,
    complete_registration as _impl_complete_registration,
    password_reset_complete as _impl_reset_complete,
    password_reset_request as _impl_reset_request,
    password_reset_verify as _impl_reset_verify,
    phone_login as _impl_phone_login,
    request_otp as _impl_register_request,
    verify_otp as _impl_register_verify,
)
from app.routers.upload import upload_avatar as _impl_upload_avatar
from app.services import order_service, product_service, review_service, user_service

log = logging.getLogger(__name__)

router = APIRouter(prefix="/mobile", tags=["mobile"])


# =====================================================================
#  AUTH — Hisobga kirish, ro'yxatdan o'tish, parolni tiklash
# =====================================================================

@router.post("/auth/login", response_model=Token)
async def mobile_login(payload: PhoneLoginPayload, request: Request, db: AsyncSession = Depends(get_db)):
    """Telefon raqam + parol orqali kirish."""
    return await _impl_phone_login(payload, request, db)


@router.post("/auth/register/request", status_code=status.HTTP_204_NO_CONTENT)
async def mobile_register_request(payload: PhonePayload, db: AsyncSession = Depends(get_db)):
    """Ro'yxatdan o'tish uchun telefon raqamiga 4 xonali SMS-OTP yuborish.
    Telefon allaqachon hisob ochilgan bo'lsa 409 qaytaradi."""
    return await _impl_register_request(payload, db)


@router.post("/auth/register/verify", response_model=VerifyOut)
async def mobile_register_verify(payload: OtpVerifyPayload, db: AsyncSession = Depends(get_db)):
    """SMS-OTP'ni tekshiradi va `registration_token` qaytaradi (10 min TTL).
    User hali yaratilmaydi."""
    return await _impl_register_verify(payload, db)


@router.post("/auth/register/complete", response_model=Token, status_code=status.HTTP_201_CREATED)
async def mobile_register_complete(payload: CompleteRegisterPayload, db: AsyncSession = Depends(get_db)):
    """registration_token + parol + ism orqali yangi user yaratish va JWT olish."""
    return await _impl_complete_registration(payload, db)


@router.post("/auth/password-reset/request", status_code=status.HTTP_204_NO_CONTENT)
async def mobile_reset_request(payload: PhonePayload, db: AsyncSession = Depends(get_db)):
    """Parolni tiklash uchun SMS yuborish. Hisob yo'q bo'lsa 404."""
    return await _impl_reset_request(payload, db)


@router.post("/auth/password-reset/verify", response_model=ResetVerifyOut)
async def mobile_reset_verify(payload: OtpVerifyPayload, db: AsyncSession = Depends(get_db)):
    """Reset OTP tasdiqlash va `reset_token` olish."""
    return await _impl_reset_verify(payload, db)


@router.post("/auth/password-reset/complete", response_model=Token)
async def mobile_reset_complete(payload: ResetCompletePayload, db: AsyncSession = Depends(get_db)):
    """Yangi parol saqlash va avtomatik JWT olish."""
    return await _impl_reset_complete(payload, db)


# =====================================================================
#  PROFILE — joriy foydalanuvchi
# =====================================================================

@router.get("/me", response_model=UserOut)
async def mobile_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me/profile", response_model=UserOut)
async def mobile_update_profile(
    data: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ism, familiya, tug'ilgan kun, photo_url yangilash.
    Yangi photo_url yuborilganda eski rasm fayli avtomatik o'chiriladi."""
    return await user_service.update_profile(db, current_user, data)


@router.post("/me/avatar", status_code=status.HTTP_201_CREATED)
async def mobile_upload_avatar(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """Profil rasmi (avatar) yuklash. JPG/PNG/WEBP/GIF, max 5 MB.
    Javob: `{"url": "/uploads/<filename>"}`.
    URL'ni keyin PATCH /mobile/me/profile da `photo_url` ga yuboring."""
    return await _impl_upload_avatar(file, user)


# =====================================================================
#  CATALOG — kategoriya, mahsulot, banner, magazin
# =====================================================================

@router.get("/products", response_model=list[ProductOut], response_model_by_alias=True)
async def mobile_products(
    category: str | None = Query(None, description="Kategoriya slug (masalan: 'large-appliances')"),
    subcategory: str | None = Query(None, description="Subkategoriya slug"),
    q: str | None = Query(None, description="Qidiruv (nom UZ/RU bo'yicha LIKE)"),
    only_sale: bool = Query(False, description="True bo'lsa faqat aksiyadagilar"),
    db: AsyncSession = Depends(get_db),
):
    """Mahsulotlar ro'yxati. Filterlar: kategoriya, subkategoriya, qidiruv, aksiya."""
    items = await product_service.list_products(db)
    # Klient tomondan filter qilamiz (mavjud servis store filterdan boshqasini bilmaydi)
    def _ok(p):
        if category and p.category != category:
            return False
        if subcategory and p.subcategory != subcategory:
            return False
        if only_sale and not getattr(p, "on_sale", False):
            return False
        if q:
            qs = q.strip().lower()
            nm = (p.name or {})
            if qs not in (nm.get("uz") or "").lower() and qs not in (nm.get("ru") or "").lower():
                return False
        return True
    return [p for p in items if _ok(p)]


@router.get("/products/{product_id}", response_model=ProductOut, response_model_by_alias=True)
async def mobile_product(product_id: int, db: AsyncSession = Depends(get_db)):
    product = await product_service.get_product(db, product_id)
    if not product:
        raise HTTPException(404, "Mahsulot topilmadi")
    return product


@router.get("/banners", response_model=list[BannerOut], response_model_by_alias=True)
async def mobile_banners(db: AsyncSession = Depends(get_db)):
    """Faqat aktiv bannerlar."""
    res = await db.execute(select(Banner).where(Banner.active.is_(True)).order_by(Banner.id.desc()))
    return list(res.scalars().all())


@router.get("/stores", response_model=list[StoreOut])
async def mobile_stores(db: AsyncSession = Depends(get_db)):
    """Faol magazinlar (asosiy + filiallar)."""
    res = await db.execute(select(Store).where(Store.active.is_(True)).order_by(Store.is_main.desc(), Store.id))
    return list(res.scalars().all())


# =====================================================================
#  ORDERS — buyurtmalar
# =====================================================================

@router.post("/orders", response_model=dict, status_code=status.HTTP_201_CREATED)
async def mobile_create_order(
    data: OrderCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Buyurtma yaratish. Body schema'si /api/orders bilan bir xil."""
    try:
        order = await order_service.create_order(db, user, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return await _serialize_order(db, order, viewer=user)


@router.get("/orders/my", response_model=list[dict])
async def mobile_my_orders(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Joriy foydalanuvchining barcha buyurtmalari."""
    orders = await order_service.list_user_orders(db, user.id)
    return [await _serialize_order(db, o, viewer=user) for o in orders]


@router.get("/orders/{order_id}", response_model=dict)
async def mobile_order_detail(
    order_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    order = await order_service.get_order(db, order_id)
    if not order or order.user_id != user.id:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
    return await _serialize_order(db, order, viewer=user)


@router.post("/orders/{order_id}/cancel", response_model=dict)
async def mobile_cancel_order(
    order_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    order = await order_service.get_order(db, order_id)
    if not order or order.user_id != user.id:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
    if order.status not in ("pending", "confirmed"):
        raise HTTPException(status_code=400, detail="Bu buyurtma allaqachon bekor qilinmaydigan holatda")
    order = await order_service.update_status(db, order, "cancelled")
    return await _serialize_order(db, order, viewer=user)


async def _serialize_order(db: AsyncSession, order, viewer: User | None = None) -> dict:
    p_name, p_addr = await order_service.get_pickup_point_info(db, order.pickup_point_id)
    out = OrderOut.model_validate(order).model_dump(by_alias=True)
    out["pickupPointName"] = p_name
    out["pickupPointAddress"] = p_addr
    # transit_code (1-kod) — oddiy foydalanuvchiga ko'rsatilmaydi
    if viewer is None or viewer.role == "user":
        out["transitCode"] = None
    return out


# =====================================================================
#  REVIEWS — sharhlar
# =====================================================================

@router.get("/reviews/product/{product_id}", response_model=list[ReviewOut])
async def mobile_product_reviews(product_id: int, db: AsyncSession = Depends(get_db)):
    """Mahsulot uchun barcha sharhlar (public)."""
    return await review_service.list_product_reviews(db, product_id)


@router.get("/reviews/my-pending", response_model=list[PendingReviewItem])
async def mobile_my_pending_reviews(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Foydalanuvchi qabul qilgan, lekin hali sharh yozmagan mahsulotlar."""
    return await review_service.list_pending_for_user(db, user.id)


@router.get("/reviews/my", response_model=list[ReviewOut])
async def mobile_my_reviews(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Foydalanuvchi yozgan barcha sharhlar."""
    return await review_service.list_my_reviews(db, user.id)


@router.post("/reviews", response_model=ReviewOut, status_code=status.HTTP_201_CREATED)
async def mobile_create_review(
    data: ReviewCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Yangi sharh yozish (faqat o'sha mahsulotni qabul qilgan foydalanuvchi)."""
    try:
        review = await review_service.create_review(db, user, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return review
