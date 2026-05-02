from fastapi import Depends, HTTPException, status

from app.models.user import User
from app.routers.user import get_current_user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """admin (sotuv admin), staff (magazin admin) yoki superadmin."""
    if user.role not in ("admin", "staff", "superadmin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


async def require_staff(user: User = Depends(get_current_user)) -> User:
    """faqat magazin admini (staff)."""
    if user.role != "staff" or not user.store_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Magazin admini ruxsati kerak")
    return user


async def require_superadmin(user: User = Depends(get_current_user)) -> User:
    if user.role != "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin access required")
    return user


async def require_pickup_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "pickup_admin" or not user.pickup_point_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Pickup admin access required")
    return user
