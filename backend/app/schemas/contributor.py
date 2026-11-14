from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ContributorTokenCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    expires_in_hours: int = Field(default=168, ge=1, le=720)


class ContributorTokenResponse(BaseModel):
    id: UUID
    brand_id: UUID
    name: str
    token: str
    expires_at: datetime


class ExternalSubmission(BaseModel):
    content: str = Field(min_length=1, max_length=20000)
    contributor_name: str = Field(min_length=2, max_length=100)


class ExternalSubmissionResponse(BaseModel):
    message: str
    review_id: UUID
    overall_status: str
    overall_score: int
    summary: str