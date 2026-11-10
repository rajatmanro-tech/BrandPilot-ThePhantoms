import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, JSON, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class VisualReview(Base):
    __tablename__ = "visual_reviews"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("brands.id"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    report: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
