from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.banner import Banner
from app.schemas.banner import BannerCreate, BannerUpdate


async def list_banners(db: AsyncSession) -> list[Banner]:
    result = await db.execute(select(Banner).order_by(Banner.id.desc()))
    return list(result.scalars().all())


async def get_banner(db: AsyncSession, banner_id: int) -> Banner | None:
    result = await db.execute(select(Banner).where(Banner.id == banner_id))
    return result.scalar_one_or_none()


async def create_banner(db: AsyncSession, data: BannerCreate) -> Banner:
    payload = data.model_dump(by_alias=False)
    payload["product_name"] = data.product_name.model_dump()
    payload["description"] = data.description.model_dump()
    banner = Banner(**payload)
    db.add(banner)
    await db.commit()
    await db.refresh(banner)
    return banner


async def update_banner(db: AsyncSession, banner: Banner, data: BannerUpdate) -> Banner:
    payload = data.model_dump(exclude_unset=True, by_alias=False)
    if "product_name" in payload and data.product_name is not None:
        payload["product_name"] = data.product_name.model_dump()
    if "description" in payload and data.description is not None:
        payload["description"] = data.description.model_dump()
    for k, v in payload.items():
        setattr(banner, k, v)
    await db.commit()
    await db.refresh(banner)
    return banner


async def delete_banner(db: AsyncSession, banner: Banner) -> None:
    await db.delete(banner)
    await db.commit()


async def toggle_active(db: AsyncSession, banner: Banner) -> Banner:
    banner.active = not banner.active
    await db.commit()
    await db.refresh(banner)
    return banner
