from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class LocalizedText(BaseModel):
    uz: str = ""
    ru: str = ""


def _config():
    return ConfigDict(
        from_attributes=True,
        alias_generator=to_camel,
        populate_by_name=True,
    )


class ProductCreate(BaseModel):
    name: LocalizedText
    description: LocalizedText = LocalizedText()
    price: int = Field(ge=0)
    old_price: int | None = Field(default=None, ge=0)
    category: str
    subcategory: str | None = None
    condition_note: str | None = None
    store_id: int | None = None
    image: str = ""
    images: list[str] = []
    stock: int = Field(default=0, ge=0)
    rating: float = Field(default=4.5, ge=0, le=5)
    credit_months: int = Field(default=12, ge=0, le=60)
    badges: list[str] = []
    on_sale: bool = False
    is_popular: bool = False
    specifications: list[dict] = []

    model_config = _config()


class ProductUpdate(BaseModel):
    name: LocalizedText | None = None
    description: LocalizedText | None = None
    price: int | None = Field(default=None, ge=0)
    old_price: int | None = None
    category: str | None = None
    subcategory: str | None = None
    condition_note: str | None = None
    image: str | None = None
    images: list[str] | None = None
    stock: int | None = Field(default=None, ge=0)
    rating: float | None = None
    credit_months: int | None = None
    badges: list[str] | None = None
    on_sale: bool | None = None
    is_popular: bool | None = None
    store_id: int | None = None
    specifications: list[dict] | None = None

    model_config = _config()


class ProductOut(BaseModel):
    id: int
    name: dict
    description: dict
    price: int
    old_price: int | None
    category: str
    subcategory: str | None
    condition_note: str | None = None
    image: str
    images: list[str] = []
    stock: int
    rating: float
    credit_months: int
    badges: list[str]
    on_sale: bool
    is_popular: bool = False
    store_id: int | None = None
    specifications: list[dict] = []
    created_at: datetime
    # Sharhlardan dinamik hisoblangan
    reviews_count: int = 0
    avg_rating: float = 0.0

    model_config = _config()
