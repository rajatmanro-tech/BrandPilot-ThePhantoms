from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.brand_rule import BrandRule
from app.schemas.brand_rule import (
    BrandRuleCreate,
    BrandRuleUpdate,
    BrandRuleResponse,
)
from app.services.brand_access import authorize_brand_action
from app.services.audit_service import create_audit_log

router = APIRouter(tags=["Brand Rules"])


@router.post(
    "/brands/{brand_id}/rules",
    response_model=BrandRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_rule(
    brand_id: UUID,
    rule_data: BrandRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    authorize_brand_action(
        db, current_user.id, brand_id, "rules:manage"
    )

    rule = BrandRule(
        brand_id=brand_id,
        created_by=current_user.id,
        **rule_data.model_dump(),
    )

    db.add(rule)
    db.flush()

    create_audit_log(
        db=db,
        brand_id=brand_id,
        user_id=current_user.id,
        action="brand_rule.created",
        entity_type="brand_rule",
        entity_id=str(rule.id),
        details={
            "title": rule.title,
            "category": rule.category,
            "severity": rule.severity,
        },
    )

    db.commit()
    db.refresh(rule)

    return rule

@router.get(
    "/brands/{brand_id}/rules",
    response_model=list[BrandRuleResponse],
)
def get_rules(
    brand_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    authorize_brand_action(
        db, current_user.id, brand_id, "brand:read"
    )

    statement = (
        select(BrandRule)
        .where(BrandRule.brand_id == brand_id)
        .order_by(BrandRule.created_at.desc())
    )

    return db.scalars(statement).all()


@router.put(
    "/rules/{rule_id}",
    response_model=BrandRuleResponse,
)
def update_rule(
    rule_id: UUID,
    rule_data: BrandRuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rule = db.get(BrandRule, rule_id)

    if rule is None:
        raise HTTPException(
            status_code=404,
            detail="Brand rule not found.",
        )

    authorize_brand_action(
        db, current_user.id, rule.brand_id, "rules:manage"
    )

    updates = rule_data.model_dump(exclude_unset=True)

    for field, value in updates.items():
        setattr(rule, field, value)

    db.flush()

    create_audit_log(
        db=db,
        brand_id=rule.brand_id,
        user_id=current_user.id,
        action="brand_rule.updated",
        entity_type="brand_rule",
        entity_id=str(rule.id),
        details={
            "updated_fields": list(updates.keys()),
        },
    )

    db.commit()
    db.refresh(rule)

    return rule

@router.delete(
    "/rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_rule(
    rule_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rule = db.get(BrandRule, rule_id)

    if rule is None:
        raise HTTPException(
            status_code=404,
            detail="Brand rule not found.",
        )

    authorize_brand_action(
        db, current_user.id, rule.brand_id, "rules:manage"
    )

    brand_id = rule.brand_id
    rule_title = rule.title

    create_audit_log(
        db=db,
        brand_id=brand_id,
        user_id=current_user.id,
        action="brand_rule.deleted",
        entity_type="brand_rule",
        entity_id=str(rule.id),
        details={
            "title": rule_title,
        },
    )

    db.delete(rule)
    db.commit()

    return None