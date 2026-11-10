
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.brand_rule import BrandRule
from app.models.review import ContentReview
from app.models.user import User
from app.schemas.review import ReviewCreate, ReviewResponse
from app.services.brand_access import authorize_brand_action
from app.services.review_service import review_content_with_fallback
from sqlalchemy import select
from app.services.audit_service import create_audit_log

router = APIRouter(tags=["Content Reviews"])


@router.post(
    "/brands/{brand_id}/reviews",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_content_review(
    brand_id: UUID,
    review_data: ReviewCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    authorize_brand_action(
        db,
        current_user.id,
        brand_id,
        "brand:read",
    )

    rules_statement = select(BrandRule).where(
        BrandRule.brand_id == brand_id,
        BrandRule.is_active.is_(True),
    )

    active_rules = db.scalars(rules_statement).all()

    brand_rules = [
        {
            "category": rule.category,
            "title": rule.title,
            "description": rule.description,
            "severity": rule.severity,
        }
        for rule in active_rules
    ]

    try:
        result, provider = review_content_with_fallback(
            review_data.content,
            brand_rules,
        )
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The AI review service failed.",
        ) from error

    new_review = ContentReview(
        brand_id=brand_id,
        user_id=current_user.id,
        content=review_data.content,
        provider=provider,
        overall_status=result.overall_status,
        overall_score=result.overall_score,
        summary=result.summary,
        findings=[
            finding.model_dump()
            for finding in result.findings
        ],
    )

    db.add(new_review)
    db.flush()

    create_audit_log(
        db=db,
        brand_id=brand_id,
        user_id=current_user.id,
        action="content.reviewed",
        entity_type="content_review",
        entity_id=str(new_review.id),
        details={
            "provider": provider,
            "overall_status": new_review.overall_status,
            "overall_score": new_review.overall_score,
        },
)

    db.commit()
    db.refresh(new_review)

    return new_review

@router.get(
    "/brands/{brand_id}/reviews",
    response_model=list[ReviewResponse],
)
def get_brand_reviews(
    brand_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    authorize_brand_action(
        db,
        current_user.id,
        brand_id,
        "brand:read",
    )

    statement = (
        select(ContentReview)
        .where(ContentReview.brand_id == brand_id)
        .order_by(ContentReview.created_at.desc())
    )

    reviews = db.scalars(statement).all()

    return reviews
@router.get(
    "/reviews/{review_id}",
    response_model=ReviewResponse,
)
def get_review(
    review_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    review = db.get(ContentReview, review_id)

    if review is None:
        raise HTTPException(
            status_code=404,
            detail="Review not found.",
        )

    authorize_brand_action(
        db,
        current_user.id,
        review.brand_id,
        "brand:read",
    )

    return review
