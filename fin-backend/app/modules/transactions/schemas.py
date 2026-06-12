from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.modules.categories.normalization import normalize_category_slug


class TransactionCreate(BaseModel):
    account_id: UUID
    amount: Decimal = Field(decimal_places=4, max_digits=19)
    description: str = Field(default="", max_length=512)
    category_slug: str = Field(default="uncategorized", max_length=64)
    occurred_at: datetime
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("category_slug")
    @classmethod
    def _normalize_category(cls, v: str) -> str:
        return normalize_category_slug(v)


class TransactionUpdate(BaseModel):
    amount: Decimal | None = Field(default=None, decimal_places=4, max_digits=19)
    description: str | None = Field(default=None, max_length=512)
    category_slug: str | None = Field(default=None, max_length=64)
    occurred_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("category_slug")
    @classmethod
    def _normalize_category(cls, v: str | None) -> str | None:
        return normalize_category_slug(v) if v is not None else None


class TransactionRead(BaseModel):
    id: UUID
    user_id: UUID
    account_id: UUID
    amount: Decimal
    description: str
    category_slug: str
    occurred_at: datetime
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
