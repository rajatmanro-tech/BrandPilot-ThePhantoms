
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.membership import BrandMembership
from app.services.rbac import check_permission


def authorize_brand_action(
    db: Session,
    user_id: UUID,
    brand_id: UUID,
    permission: str,
) -> BrandMembership:
    statement = select(BrandMembership).where(
        BrandMembership.brand_id == brand_id,
        BrandMembership.user_id == user_id,
    )

    membership = db.scalar(statement)

    if membership is None:
        raise HTTPException(
            status_code=403,
            detail="You are not a member of this brand.",
        )

    if not check_permission(membership.role, permission):
        raise HTTPException(
            status_code=403,
            detail="Your role does not permit this action.",
        )

    return membership
