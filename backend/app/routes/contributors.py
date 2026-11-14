import hashlib
import secrets
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.contributor_token import ContributorToken
from app.models.brand_rule import BrandRule
from app.models.review import ContentReview
from app.models.user import User
from app.schemas.contributor import (
    ContributorTokenCreate,
    ContributorTokenResponse,
    ExternalSubmission,
    ExternalSubmissionResponse,
)
from app.services.brand_access import authorize_brand_action
from app.services.audit_service import create_audit_log
from app.services.review_service import review_content_with_fallback


router = APIRouter(tags=["External Contributors"])


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@router.post(
    "/brands/{brand_id}/contributors/tokens",
    response_model=ContributorTokenResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_contributor_token(
    brand_id: UUID,
    data: ContributorTokenCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    authorize_brand_action(
        db, current_user.id, brand_id, "members:manage"
    )

    raw_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc).replace(
        microsecond=0
    )

    from datetime import timedelta
    expires_at += timedelta(hours=data.expires_in_hours)

    contributor_token = ContributorToken(
        brand_id=brand_id,
        created_by=current_user.id,
        name=data.name,
        token_hash=hash_token(raw_token),
        expires_at=expires_at,
    )

    db.add(contributor_token)
    db.flush()

    create_audit_log(
        db=db,
        brand_id=brand_id,
        user_id=current_user.id,
        action="contributor.token_created",
        entity_type="contributor_token",
        entity_id=str(contributor_token.id),
        details={"name": data.name, "expires_at": expires_at.isoformat()},
    )

    db.commit()
    db.refresh(contributor_token)

    return ContributorTokenResponse(
        id=contributor_token.id,
        brand_id=brand_id,
        name=contributor_token.name,
        token=raw_token,
        expires_at=contributor_token.expires_at,
    )


@router.delete("/contributors/tokens/{token_id}")
def revoke_contributor_token(
    token_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contributor_token = db.get(ContributorToken, token_id)

    if contributor_token is None:
        raise HTTPException(status_code=404, detail="Token not found.")

    authorize_brand_action(
        db,
        current_user.id,
        contributor_token.brand_id,
        "members:manage",
    )

    if contributor_token.revoked_at is not None:
        raise HTTPException(status_code=409, detail="Token already revoked.")

    contributor_token.revoked_at = datetime.now(timezone.utc)

    create_audit_log(
        db=db,
        brand_id=contributor_token.brand_id,
        user_id=current_user.id,
        action="contributor.token_revoked",
        entity_type="contributor_token",
        entity_id=str(contributor_token.id),
        details={"name": contributor_token.name},
    )

    db.commit()

    return {"message": "Contributor token revoked successfully."}


@router.post(
    "/external/submit",
    response_model=ExternalSubmissionResponse,
)
def external_submit(
    data: ExternalSubmission,
    x_contributor_token: str = Header(..., alias="X-Contributor-Token"),
    db: Session = Depends(get_db),
):
    token_hash = hash_token(x_contributor_token)

    contributor_token = db.scalar(
        select(ContributorToken).where(
            ContributorToken.token_hash == token_hash
        )
    )

    if contributor_token is None:
        raise HTTPException(status_code=401, detail="Invalid contributor token.")

    now = datetime.now(timezone.utc)

    if contributor_token.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Contributor token has been revoked.")

    if contributor_token.expires_at <= now:
        raise HTTPException(status_code=401, detail="Contributor token has expired.")

    rules = db.scalars(
        select(BrandRule).where(
            BrandRule.brand_id == contributor_token.brand_id,
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
            data.content, brand_rules
        )
    except RuntimeError as error:
        raise HTTPException(
            status_code=503,
            detail="AI review services are temporarily unavailable.",
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail="The AI review service failed.",
        ) from error

    review = ContentReview(
        brand_id=contributor_token.brand_id,
        user_id=contributor_token.created_by,
        content=data.content,
        provider=provider,
        overall_status=result.overall_status,
        overall_score=result.overall_score,
        summary=result.summary,
        findings=[finding.model_dump() for finding in result.findings],
    )

    db.add(review)
    db.flush()

    create_audit_log(
        db=db,
        brand_id=contributor_token.brand_id,
        user_id=contributor_token.created_by,
        action="contributor.content_submitted",
        entity_type="content_review",
        entity_id=str(review.id),
        details={
            "contributor_name": data.contributor_name,
            "token_id": str(contributor_token.id),
            "provider": provider,
            "overall_status": review.overall_status,
            "overall_score": review.overall_score,
        },
    )

    db.commit()

    return ExternalSubmissionResponse(
        message="Content submitted and reviewed successfully.",
        review_id=review.id,
        overall_status=review.overall_status,
        overall_score=review.overall_score,
        summary=review.summary,
    )