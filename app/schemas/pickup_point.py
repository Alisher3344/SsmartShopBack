from datetime import datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.schemas.product import LocalizedText


def _config():
    return ConfigDict(
        from_attributes=True,
        alias_generator=to_camel,
        populate_by_name=True,
    )


class PickupPointCreate(BaseModel):
    name: LocalizedText
    address: LocalizedText
    phone: str | None = None
    work_hours: str | None = None
    active: bool = True

    model_config = _config()


class PickupPointUpdate(BaseModel):
    name: LocalizedText | None = None
    address: LocalizedText | None = None
    phone: str | None = None
    work_hours: str | None = None
    active: bool | None = None

    model_config = _config()


class PickupPointOut(BaseModel):
    id: int
    name: dict
    address: dict
    phone: str | None
    work_hours: str | None
    active: bool
    created_at: datetime

    model_config = _config()
