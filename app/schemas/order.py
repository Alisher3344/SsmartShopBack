from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


def _config():
    return ConfigDict(
        from_attributes=True,
        alias_generator=to_camel,
        populate_by_name=True,
    )


class OrderItemIn(BaseModel):
    product_id: int
    qty: int = Field(ge=1)

    model_config = _config()


class OrderCreate(BaseModel):
    items: list[OrderItemIn]
    delivery_type: str = Field(pattern="^(pickup|courier)$")
    pickup_point_id: int | None = None
    delivery_address: str | None = None
    payment_method: str = Field(pattern="^(card|cash)$")
    comment: str | None = None

    model_config = _config()


class OrderItemOut(BaseModel):
    product_id: int
    name: dict
    qty: int
    price: int
    image: str = ""

    model_config = _config()


class OrderOut(BaseModel):
    id: int
    user_id: int
    pickup_point_id: int | None
    store_id: int | None = None
    delivery_type: str
    delivery_address: str | None
    payment_method: str
    items: list[OrderItemOut]
    total: int
    comment: str | None
    customer_name: str | None
    customer_phone: str | None
    status: str
    transit_code: str | None = None
    pickup_code: str | None = None
    received_at: datetime | None = None
    delivered_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    # Pickup point ma'lumotlari (admin uchun)
    pickup_point_name: dict | None = None
    pickup_point_address: dict | None = None

    model_config = _config()
