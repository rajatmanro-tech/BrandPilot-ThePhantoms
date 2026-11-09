from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.audit_log import (
    AuditLogResponse,
    AuditVerificationResponse,
)
from app.services.audit_service import verify_audit_chain
from app.services.brand_access import authorize_brand_action

router = APIRouter(tags=["Audit Logs"])


@router.get(
    "/brands/{brand_id}/audit-logs",
    response_model=list[AuditLogResponse],
)
def get_audit_logs(
    brand_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    authorize_brand_action(
        db, current_user.id, brand_id, "reports:read"
    )

    statement = (
        select(AuditLog)
        .where(AuditLog.brand_id == brand_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
    )

    return db.scalars(statement).all()


@router.get(
    "/brands/{brand_id}/audit-logs/verify",
    response_model=AuditVerificationResponse,
)
def verify_brand_audit_logs(
    brand_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    authorize_brand_action(
        db, current_user.id, brand_id, "reports:read"
    )

    return verify_audit_chain(db, brand_id)