
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from io import BytesIO

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.brand_rule import BrandRule
from app.models.document import Document
from app.models.review import ContentReview
from app.models.review_decision import ReviewDecision
from app.models.user import User
from app.services.audit_service import create_audit_log
from app.services.brand_access import authorize_brand_action
from app.services.document_service import (
    MAX_FILE_SIZE,
    extract_document_text,
    stamp_approved_document,
)
from app.services.review_service import review_content_with_fallback

router = APIRouter(tags=["Documents"])


@router.post(
    "/brands/{brand_id}/documents",
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    brand_id: UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    authorize_brand_action(
        db, current_user.id, brand_id, "brand:read"
    )

    filename = Path(file.filename or "upload").name
    file_data = await file.read(MAX_FILE_SIZE + 1)

    try:
        extracted = extract_document_text(file_data, filename)
    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    rules = db.scalars(
        select(BrandRule).where(
            BrandRule.brand_id == brand_id,
            BrandRule.is_active.is_(True),
        )
    ).all()

    brand_rules = [
        {
            "category": rule.category,
            "title": rule.title,
            "description": rule.description,
            "severity": rule.severity,
        }
        for rule in rules
    ]

    try:
        result, provider = review_content_with_fallback(
            extracted["text"],
            brand_rules,
        )
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail="The AI review service failed.",
        ) from error

    try:
        review = ContentReview(
            brand_id=brand_id,
            user_id=current_user.id,
            content=extracted["text"],
            provider=provider,
            overall_status=result.overall_status,
            overall_score=result.overall_score,
            summary=result.summary,
            findings=[
                finding.model_dump()
                for finding in result.findings
            ],
        )

        db.add(review)
        db.flush()

        document = Document(
            brand_id=brand_id,
            user_id=current_user.id,
            review_id=review.id,
            filename=filename,
            file_type=extracted["file_type"],
            file_size=len(file_data),
            file_data=file_data,
            content_hash=hashlib.sha256(file_data).hexdigest(),
            approval_status="pending",
        )

        db.add(document)
        db.flush()

        create_audit_log(
            db=db,
            brand_id=brand_id,
            user_id=current_user.id,
            action="document.uploaded",
            entity_type="document",
            entity_id=str(document.id),
            details={
                "filename": filename,
                "review_id": str(review.id),
                "provider": provider,
            },
        )

        db.commit()
        db.refresh(document)
        db.refresh(review)

    except Exception:
        db.rollback()
        raise

    return {
        "message": "Document uploaded and reviewed successfully.",
        "document": {
            "id": str(document.id),
            "filename": document.filename,
            "file_type": document.file_type,
            "file_size": document.file_size,
            "approval_status": document.approval_status,
            "content_hash": document.content_hash,
            "created_at": document.created_at,
        },
        "review": {
            "id": str(review.id),
            "provider": review.provider,
            "overall_status": review.overall_status,
            "overall_score": review.overall_score,
            "summary": review.summary,
            "findings": review.findings,
        },
    }


@router.get("/brands/{brand_id}/documents")
def list_documents(
    brand_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    authorize_brand_action(
        db, current_user.id, brand_id, "brand:read"
    )

    documents = db.scalars(
        select(Document)
        .where(Document.brand_id == brand_id)
        .order_by(Document.created_at.desc())
    ).all()

    return [
        {
            "id": str(document.id),
            "filename": document.filename,
            "file_type": document.file_type,
            "approval_status": document.approval_status,
            "created_at": document.created_at,
            "approved_at": document.approved_at,
        }
        for document in documents
    ]


@router.post("/documents/{document_id}/approve")
def approve_document(
    document_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = db.get(Document, document_id)

    if document is None:
        raise HTTPException(404, "Document not found.")

    authorize_brand_action(
        db, current_user.id, document.brand_id, "reviews:decide"
    )

    if document.approval_status == "approved":
        return {
            "message": "Document is already approved.",
            "approval_status": "approved",
            "approved_at": document.approved_at,
        }

    review = db.get(ContentReview, document.review_id)

    if review is None:
        raise HTTPException(409, "Associated review not found.")

    decisions = db.scalars(
        select(ReviewDecision).where(
            ReviewDecision.review_id == review.id
        )
    ).all()

    resolved_indices = {
        decision.finding_index for decision in decisions
    }

    unresolved = [
        index
        for index in range(len(review.findings))
        if index not in resolved_indices
    ]

    if unresolved:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Resolve all findings before approval.",
                "unresolved_findings": unresolved,
            },
        )

    document.approval_status = "approved"
    document.approved_by = current_user.id
    document.approved_at = datetime.now(timezone.utc)

    create_audit_log(
        db=db,
        brand_id=document.brand_id,
        user_id=current_user.id,
        action="document.approved",
        entity_type="document",
        entity_id=str(document.id),
        details={
            "filename": document.filename,
            "review_id": str(review.id),
        },
    )

    db.commit()
    db.refresh(document)

    return {
        "message": "Document approved successfully.",
        "approval_status": document.approval_status,
        "approved_at": document.approved_at,
    }


@router.get("/documents/{document_id}/export")
def export_approved_document(
    document_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = db.get(Document, document_id)

    if document is None:
        raise HTTPException(404, "Document not found.")

    authorize_brand_action(
        db, current_user.id, document.brand_id, "brand:read"
    )

    if document.approval_status != "approved":
        raise HTTPException(
            status_code=403,
            detail="Only approved documents can be exported.",
        )

    actual_hash = hashlib.sha256(document.file_data).hexdigest()

    if actual_hash != document.content_hash:
        raise HTTPException(
            status_code=409,
            detail="Document integrity verification failed.",
        )

    approver = db.get(User, document.approved_by)
    approver_name = approver.full_name if approver else "BrandPilot"

    approved_at = (
        document.approved_at.isoformat()
        if document.approved_at
        else datetime.now(timezone.utc).isoformat()
    )

    try:
        stamped = stamp_approved_document(
            file_data=document.file_data,
            file_type=document.file_type,
            approved_by=approver_name,
            approved_at=approved_at,
        )
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail="Unable to generate approved export.",
        ) from error

    extension = document.file_type
    filename = f"APPROVED_{Path(document.filename).stem}.{extension}"

    media_type = (
        "application/pdf"
        if extension == "pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    return StreamingResponse(
        BytesIO(stamped),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )
