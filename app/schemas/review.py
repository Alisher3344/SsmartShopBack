from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


def _config():
    return ConfigDict(
        from_attributes=True,
        alias_generator=to_camel,
        populate_by_name=True,
    )


class ReviewCreate(BaseModel):
    product_id: int
    order_id: int | None = None
    rating: int = Field(ge=1, le=5)
    text: str | None = Field(default=None, max_length=2000)

    model_config = _config()


class ReviewOut(BaseModel):
    id: int
    user_id: int
    product_id: int
    order_id: int | None
    rating: int
    text: str | None
    created_at: datetime
    # Foydalanuvchi nomi
    user_name: str | None = None
    # Mahsulot ma'lumotlari (mening sharhlarim ro'yxati uchun)
    product_name: dict | None = None
    product_image: str | None = None

    model_config = _config()


class PendingReviewItem(BaseModel):
    product_id: int
    order_id: int
    name: dict
    image: str | None = None
    delivered_at: datetime | None = None

    model_config = _config()
