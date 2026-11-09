
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class ReviewCreate(BaseModel):
    content: str = Field(
        min_length=1,
        description="Content submitted for brand governance review.",
    )


class ReviewFindingResponse(BaseModel):
    category: str
    severity: Literal["low", "medium", "high", "critical"]
    issue: str
    explanation: str
    suggestion: str
    original_text: str


class ReviewResponse(BaseModel):
    id: UUID
    brand_id: UUID
    user_id: UUID
    content: str
    provider: str
    overall_status: Literal["pass", "needs_changes", "fail"]
    overall_score: int = Field(ge=0, le=100)
    summary: str
    findings: list[ReviewFindingResponse]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
