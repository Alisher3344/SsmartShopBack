"""Ssmart Pro (pro.ssmart.uz) bosh sahifa reklama karuseli — Pro backendiga proxy.

Super-admin dashboard (ssmart-dashboard.ssmart.uz) Pro bo'limidan karuselni
boshqaradi. Slaydlar Pro (master-api) bazasida yashaydi, shuning uchun CRUD Pro
backendning ichki (server-to-server, X-Internal-Secret) endpointiga uzatiladi.
"""
import logging

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, status

from app.core.config import settings
from app.core.deps import require_superadmin

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/pro-carousel",
    tags=["pro-carousel"],
    dependencies=[Depends(require_superadmin)],
)

_PRO_BASE_PATH = "/api/v1/internal/carousel"


def _client() -> httpx.AsyncClient:
    if not settings.PRO_INTERNAL_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pro integratsiyasi sozlanmagan (PRO_INTERNAL_SECRET yo'q)",
        )
    return httpx.AsyncClient(
        base_url=settings.PRO_API_URL,
        timeout=settings.PRO_API_TIMEOUT,
        headers={"X-Internal-Secret": settings.PRO_INTERNAL_SECRET},
    )


def _relay_error(resp: httpx.Response) -> None:
    try:
        detail = resp.json().get("detail")
    except Exception:
        detail = None
    raise HTTPException(status_code=resp.status_code, detail=detail or "Pro xatosi")


@router.get("")
async def list_slides():
    try:
        async with _client() as c:
            r = await c.get(_PRO_BASE_PATH)
    except httpx.HTTPError as e:
        log.warning("Pro carousel list failed: %s", e)
        raise HTTPException(status_code=502, detail="Pro backendiga ulanib bo'lmadi")
    if r.status_code != 200:
        _relay_error(r)
    return r.json()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_slide(data: dict = Body(...)):
    try:
        async with _client() as c:
            r = await c.post(_PRO_BASE_PATH, json=data)
    except httpx.HTTPError as e:
        log.warning("Pro carousel create failed: %s", e)
        raise HTTPException(status_code=502, detail="Pro backendiga ulanib bo'lmadi")
    if r.status_code != 201:
        _relay_error(r)
    return r.json()


@router.put("/{slide_id}")
async def update_slide(slide_id: int, data: dict = Body(...)):
    try:
        async with _client() as c:
            r = await c.put(f"{_PRO_BASE_PATH}/{slide_id}", json=data)
    except httpx.HTTPError as e:
        log.warning("Pro carousel update failed: %s", e)
        raise HTTPException(status_code=502, detail="Pro backendiga ulanib bo'lmadi")
    if r.status_code != 200:
        _relay_error(r)
    return r.json()


@router.delete("/{slide_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_slide(slide_id: int):
    try:
        async with _client() as c:
            r = await c.delete(f"{_PRO_BASE_PATH}/{slide_id}")
    except httpx.HTTPError as e:
        log.warning("Pro carousel delete failed: %s", e)
        raise HTTPException(status_code=502, detail="Pro backendiga ulanib bo'lmadi")
    if r.status_code not in (200, 204):
        _relay_error(r)
    return None
