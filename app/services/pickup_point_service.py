from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pickup_point import PickupPoint
from app.schemas.pickup_point import PickupPointCreate, PickupPointUpdate


async def list_points(db: AsyncSession, only_active: bool = False) -> list[PickupPoint]:
    stmt = select(PickupPoint).order_by(PickupPoint.id.asc())
    if only_active:
        stmt = stmt.where(PickupPoint.active.is_(True))
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_point(db: AsyncSession, point_id: int) -> PickupPoint | None:
    result = await db.execute(select(PickupPoint).where(PickupPoint.id == point_id))
    return result.scalar_one_or_none()


async def create_point(db: AsyncSession, data: PickupPointCreate) -> PickupPoint:
    payload = data.model_dump(by_alias=False)
    payload["name"] = data.name.model_dump()
    payload["address"] = data.address.model_dump()
    point = PickupPoint(**payload)
    db.add(point)
    await db.commit()
    await db.refresh(point)
    return point


async def update_point(db: AsyncSession, point: PickupPoint, data: PickupPointUpdate) -> PickupPoint:
    payload = data.model_dump(exclude_unset=True, by_alias=False)
    if "name" in payload and data.name is not None:
        payload["name"] = data.name.model_dump()
    if "address" in payload and data.address is not None:
        payload["address"] = data.address.model_dump()
    for k, v in payload.items():
        setattr(point, k, v)
    await db.commit()
    await db.refresh(point)
    return point


async def delete_point(db: AsyncSession, point: PickupPoint) -> None:
    await db.delete(point)
    await db.commit()


async def ensure_default_point(db: AsyncSession) -> None:
    """Birinchi ishga tushganda default punkt yaratamiz."""
    existing = await list_points(db)
    if existing:
        return
    point = PickupPoint(
        name={"uz": "Asosiy ofis", "ru": "Главный офис"},
        address={
            "uz": "Qarshi sh., I.Karimov ko'chasi 276-uy",
            "ru": "г. Карши, ул. И.Каримова, 276",
        },
        phone="+998948080055",
        work_hours="09:00 - 21:00",
        active=True,
    )
    db.add(point)
    await db.commit()
    print("[seed] Default topshirish punkti yaratildi")
