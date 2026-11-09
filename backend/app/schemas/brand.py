from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime


class BrandCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    slug: str = Field(min_length=2, max_length=160)


class BrandResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    created_by: UUID
    created_at: datetime

    model_config = {"from_attributes": True}
class BrandUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=150)