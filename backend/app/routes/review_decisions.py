from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.review import ContentReview
from app.models.review_decision import ReviewDecision
from app.models.user import User
from app.schemas.review_decision import ReviewDecisionCreate, ReviewDecisionResponse
from app.services.brand_access import authorize_brand_action
from app.services.audit_service import create_audit_log

router = APIRouter(tags=["Review Decisions"])


@router.post("/reviews/{review_id}/decisions", response_model=ReviewDecisionResponse)
def save_review_decision(
    review_id: UUID,
    payload: ReviewDecisionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    review = db.get(ContentReview, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found.")
    authorize_brand_action(db, current_user.id, review.brand_id, "reviews:decide")
    if payload.finding_index >= len(review.findings):
        raise HTTPException(status_code=422, detail="finding_index is outside this review's findings.")

    statement = select(ReviewDecision).where(
        ReviewDecision.review_id == review_id,
        ReviewDecision.finding_index == payload.finding_index,
    )
    decision = db.scalar(statement)
    if decision is None:
        decision = ReviewDecision(
            review_id=review_id,
            user_id=current_user.id,
            finding_index=payload.finding_index,
            decision=payload.decision,
            reason=payload.reason,
            replacement_text=payload.replacement_text,
        )
        db.add(decision)
    else:
        decision.user_id = current_user.id
        decision.decision = payload.decision
        decision.reason = payload.reason
        decision.replacement_text = payload.replacement_text

    db.flush()
    create_audit_log(
        db=db,
        brand_id=review.brand_id,
        user_id=current_user.id,
        action=f"review_finding.{payload.decision}",
        entity_type="review_decision",
        entity_id=str(decision.id),
        details={
            "review_id": str(review_id),
            "finding_index": payload.finding_index,
            "reason": payload.reason,
            "replacement_text": payload.replacement_text,
        },
    )
    db.commit()
    db.refresh(decision)
    return decision


@router.get("/reviews/{review_id}/decisions", response_model=list[ReviewDecisionResponse])
def get_review_decisions(
    review_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    review = db.get(ContentReview, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found.")
    authorize_brand_action(db, current_user.id, review.brand_id, "brand:read")
    return db.scalars(
        select(ReviewDecision)
        .where(ReviewDecision.review_id == review_id)
        .order_by(ReviewDecision.finding_index.asc())
    ).all()
