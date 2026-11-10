from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    id: UUID
    brand_id: UUID
    user_id: UUID
    action: str
    entity_type: str
    entity_id: str
    details: dict
    previous_hash: Optional[str]
    event_hash: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditVerificationResponse(BaseModel):
    valid: bool
    checked_events: int
    broken_event_id: Optional[str]