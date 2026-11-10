from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class VisualReviewResponse(BaseModel):
    id: UUID
    brand_id: UUID
    user_id: UUID
    filename: str
    report: dict
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
