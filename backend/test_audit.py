from sqlalchemy import delete

from app.db.session import SessionLocal
from app.models.audit_log import AuditLog

db = SessionLocal()

try:
    statement = delete(AuditLog).where(
        AuditLog.action.in_([
            "test.create",
            "test.update",
        ])
    )

    result = db.execute(statement)
    db.commit()

    print(f"Deleted {result.rowcount} test audit records.")

finally:
    db.close()