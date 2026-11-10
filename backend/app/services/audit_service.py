import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def generate_event_hash(
    brand_id: UUID,
    user_id: UUID,
    action: str,
    entity_type: str,
    entity_id: str,
    details: dict,
    previous_hash: str | None,
    created_at: datetime,
) -> str:

    payload = {
        "brand_id": str(brand_id),
        "user_id": str(user_id),
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "details": details,
        "previous_hash": previous_hash,
        "created_at": created_at.astimezone(timezone.utc).isoformat(),
    }

    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )

    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def create_audit_log(
    db: Session,
    brand_id: UUID,
    user_id: UUID,
    action: str,
    entity_type: str,
    entity_id: str,
    details: dict | None = None,
) -> AuditLog:

    statement = (
        select(AuditLog)
        .where(AuditLog.brand_id == brand_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    )

    previous_log = db.scalars(statement).first()

    previous_hash = (
        previous_log.event_hash if previous_log else None
    )

    created_at = datetime.now(timezone.utc)
    details = details or {}

    event_hash = generate_event_hash(
        brand_id=brand_id,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        previous_hash=previous_hash,
        created_at=created_at,
    )

    audit_log = AuditLog(
        brand_id=brand_id,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        previous_hash=previous_hash,
        event_hash=event_hash,
        created_at=created_at,
    )

    db.add(audit_log)
    db.flush()

    return audit_log
def verify_audit_chain(
    db: Session,
    brand_id: UUID,
) -> dict:

    statement = (
        select(AuditLog)
        .where(AuditLog.brand_id == brand_id)
        .order_by(
            AuditLog.created_at.asc(),
            AuditLog.id.asc(),
        )
    )

    logs = db.scalars(statement).all()

    expected_previous_hash = None

    for log in logs:

        if log.previous_hash != expected_previous_hash:
            return {
                "valid": False,
                "checked_events": logs.index(log),
                "broken_event_id": str(log.id),
            }

        expected_hash = generate_event_hash(
            brand_id=log.brand_id,
            user_id=log.user_id,
            action=log.action,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            details=log.details,
            previous_hash=log.previous_hash,
            created_at=log.created_at,
        )

        if log.event_hash != expected_hash:
            return {
                "valid": False,
                "checked_events": logs.index(log) + 1,
                "broken_event_id": str(log.id),
            }

        expected_previous_hash = log.event_hash

    return {
        "valid": True,
        "checked_events": len(logs),
        "broken_event_id": None,
    }