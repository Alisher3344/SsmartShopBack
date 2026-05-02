from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.user import User
from app.routers.user import get_current_user
from app.schemas.review import ReviewCreate
from app.services import review_service

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("/my-pending")
async def my_pending(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Yetkazib berilgan, lekin sharh yozilmagan mahsulotlar."""
    return await review_service.list_pending_for_user(db, user.id)


@router.get("/my")
async def my_reviews(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await review_service.list_my_reviews(db, user.id)


@router.get("/product/{product_id}")
async def product_reviews(product_id: int, db: AsyncSession = Depends(get_db)):
    """Mahsulot sahifasida ko'rsatish — public."""
    return await review_service.list_product_reviews(db, product_id)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_review(
    data: ReviewCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        review = await review_service.create_review(db, user, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "id": review.id,
        "userId": review.user_id,
        "productId": review.product_id,
        "orderId": review.order_id,
        "rating": review.rating,
        "text": review.text,
        "createdAt": review.created_at,
    }
