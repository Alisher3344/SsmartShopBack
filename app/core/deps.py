from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.database import get_db
from app.models.user import User
from app.services import user_service

ADMIN_ROLES = ("admin", "staff", "superadmin")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/users/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = await user_service.get_user_by_id(db, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


def require_roles(*roles: str):
    """Belgilangan rollardan biri talab qilinadi. Aks holda 403."""
    async def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Ruxsat yo'q")
        return user
    return _dep


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """admin (sotuv admin), staff (magazin admin) yoki superadmin."""
    if user.role not in ADMIN_ROLES:
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
