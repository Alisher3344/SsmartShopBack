from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.schemas.product import LocalizedText


def _config():
    return ConfigDict(
        from_attributes=True,
        alias_generator=to_camel,
        populate_by_name=True,
    )


class BannerCreate(BaseModel):
    image: str = ""
    image_uz: str = ""
    image_ru: str = ""
    product_name: LocalizedText = LocalizedText()
    description: LocalizedText = LocalizedText()
    old_price: int | None = Field(default=None, ge=0)
    sale_price: int = Field(default=0, ge=0)
    credit_months: int = Field(default=12, ge=0, le=60)
    link: str = "/catalog"
    active: bool = True
    slot: str = "home"

    model_config = _config()


class BannerUpdate(BaseModel):
    image: str | None = None
    image_uz: str | None = None
    image_ru: str | None = None
    product_name: LocalizedText | None = None
    description: LocalizedText | None = None
    old_price: int | None = None
    sale_price: int | None = Field(default=None, ge=0)
    credit_months: int | None = None
    link: str | None = None
    active: bool | None = None
    slot: str | None = None

    model_config = _config()


class BannerOut(BaseModel):
    id: int
    image: str
    image_uz: str
    image_ru: str
    product_name: dict
    description: dict
    old_price: int | None
    sale_price: int
    credit_months: int
    link: str
    active: bool
    slot: str
    created_at: datetime

    model_config = _config()
