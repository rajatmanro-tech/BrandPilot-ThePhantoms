from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional


class BrandRuleCreate(BaseModel):
    category: str = Field(min_length=2, max_length=100)
    title: str = Field(min_length=2, max_length=150)
    description: str = Field(min_length=5)
    severity: str = Field(default="medium", max_length=30)
    rule_code: Optional[str] = Field(default=None, max_length=20)


class BrandRuleUpdate(BaseModel):
    category: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[str] = None
    rule_code: Optional[str] = None
    is_active: Optional[bool] = None


class BrandRuleResponse(BaseModel):
    id: UUID
    brand_id: UUID
    created_by: UUID
    category: str
    title: str
    description: str
    severity: str
    rule_code: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}