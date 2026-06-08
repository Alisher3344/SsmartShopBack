"""SsmartTV admin provisioning — proxied to the TV backend.

The super-admin manages SsmartTV admin accounts from the dashboard. TV accounts
live in the TV database, so we forward create/list/delete to the TV backend's
internal endpoint (server-to-server) authenticated by a shared secret. The
super-admin authenticates to THIS endpoint normally (JWT + require_superadmin).
"""
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import settings
from app.core.deps import require_superadmin
from app.schemas.user import TvAdminCreate, TvAdminUpdate

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admins",
    tags=["tv-admins"],
    dependencies=[Depends(require_superadmin)],
)

_TV_BASE_PATH = "/api/v1/internal/tv-admins"


def _client() -> httpx.AsyncClient:
    if not settings.TV_INTERNAL_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TV integratsiyasi sozlanmagan (TV_INTERNAL_SECRET yo'q)",
        )
    return httpx.AsyncClient(
        base_url=settings.TV_API_URL,
        timeout=settings.TV_API_TIMEOUT,
        headers={"X-Internal-Secret": settings.TV_INTERNAL_SECRET},
    )


def _relay_error(resp: httpx.Response) -> None:
    """Surface the TV backend's error to the caller with the same status."""
    try:
        detail = resp.json().get("detail")
    except Exception:
        detail = None
    raise HTTPException(status_code=resp.status_code, detail=detail or "TV xatosi")


@router.get("")
async def list_tv_admins():
    try:
        async with _client() as c:
            r = await c.get(_TV_BASE_PATH)
    except httpx.HTTPError as e:
        log.warning("TV list failed: %s", e)
        raise HTTPException(status_code=502, detail="TV backendiga ulanib bo'lmadi")
    if r.status_code != 200:
        _relay_error(r)
    return r.json()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_tv_admin(data: TvAdminCreate):
    payload = data.model_dump()
    try:
        async with _client() as c:
            r = await c.post(_TV_BASE_PATH, json=payload)
    except httpx.HTTPError as e:
        log.warning("TV create failed: %s", e)
        raise HTTPException(status_code=502, detail="TV backendiga ulanib bo'lmadi")
    if r.status_code != 201:
        _relay_error(r)
    return r.json()


@router.put("/{user_id}")
async def update_tv_admin(user_id: int, data: TvAdminUpdate):
    # Faqat foydalanuvchi yuborgan maydonlarni uzatamiz (parol bo'sh bo'lsa o'zgarmaydi).
    payload = data.model_dump(exclude_unset=True)
    try:
        async with _client() as c:
            r = await c.put(f"{_TV_BASE_PATH}/{user_id}", json=payload)
    except httpx.HTTPError as e:
        log.warning("TV update failed: %s", e)
        raise HTTPException(status_code=502, detail="TV backendiga ulanib bo'lmadi")
    if r.status_code != 200:
        _relay_error(r)
    return r.json()


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tv_admin(user_id: int):
    try:
        async with _client() as c:
            r = await c.delete(f"{_TV_BASE_PATH}/{user_id}")
    except httpx.HTTPError as e:
        log.warning("TV delete failed: %s", e)
        raise HTTPException(status_code=502, detail="TV backendiga ulanib bo'lmadi")
    if r.status_code not in (200, 204):
        _relay_error(r)
    return None
