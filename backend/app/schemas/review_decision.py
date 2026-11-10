from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict, model_validator


class ReviewDecisionCreate(BaseModel):
    finding_index: int = Field(ge=0)
    decision: Literal["accepted", "overridden"]
    reason: str | None = None
    replacement_text: str | None = None

    @model_validator(mode="after")
    def validate_decision(self):
        if self.decision == "overridden" and not (self.reason and self.reason.strip()):
            raise ValueError("A reason is required when overriding a finding.")
        if self.decision == "accepted" and not (self.replacement_text and self.replacement_text.strip()):
            raise ValueError("Provide the replacement text that was accepted.")
        return self


class ReviewDecisionResponse(BaseModel):
    id: UUID
    review_id: UUID
    user_id: UUID
    finding_index: int
    decision: Literal["accepted", "overridden"]
    reason: str | None
    replacement_text: str | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
