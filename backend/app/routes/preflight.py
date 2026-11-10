from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.brand_rule import BrandRule
from app.models.user import User
from app.services.brand_access import authorize_brand_action
from app.services.audit_service import create_audit_log
from app.services import preflight as engine

router = APIRouter(tags=["Deterministic Preflight"])

# These are the rule identifiers implemented by the deterministic engine.
RULE_TO_REVIEWER = {
    "X-003": "claims", "X-007": "claims",
    "T-031": "terminology", "T-044": "terminology",
    "V-002": "tone", "A-003": "readability",
}
SUPPORTED_CODES = set(RULE_TO_REVIEWER)


class PreflightCreate(BaseModel):
    content: str = Field(min_length=1, max_length=100000)
    channel: str = Field(default="social", max_length=40)


@router.post("/brands/{brand_id}/preflight")
def run_brand_preflight(
    brand_id: UUID,
    payload: PreflightCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    authorize_brand_action(db, current_user.id, brand_id, "brand:read")
    rules = db.scalars(select(BrandRule).where(
        BrandRule.brand_id == brand_id,
        BrandRule.is_active.is_(True),
    )).all()

    configured = [r for r in rules if r.rule_code in SUPPORTED_CODES]
    if not configured:
        raise HTTPException(
            status_code=422,
            detail="No supported deterministic rule codes are configured for this brand. Add rule_code X-003, X-007, T-031, T-044, V-002 or A-003 to a brand rule.",
        )

    registry = {}
    reviewers_to_run = set()
    for db_rule in configured:
        code = db_rule.rule_code
        base_rule = engine.default_rules()[code]
        registry[code] = engine.Rule(
            rule_id=code,
            domain=base_rule.domain,
            severity=(db_rule.severity or base_rule.severity).upper(),
            title=db_rule.title,
            source_doc="Brand rules",
            source_clause=str(db_rule.id),
            why=db_rule.description,
        )
        reviewers_to_run.add(RULE_TO_REVIEWER[code])

    kit = engine.BrandKit(
        name="Database brand rules",
        version="database",
        rules=registry,
        approved_claims={},  # never inject the demo brand's approved claims
        outdated_since_years=(),
    )
    selected_reviewers = {
        name: fn for name, fn in engine.DEFAULT_REVIEWERS.items()
        if name in reviewers_to_run
    }
    # Fact checks are deliberately not enabled: the current DB schema has no
    # approved founding-year field, so using the demo year would be unsafe.
    report = engine.run_preflight(
        payload.content,
        source="api",
        channel=payload.channel,
        kit=kit,
        reviewers=selected_reviewers,
    ).to_dict()

    create_audit_log(
        db=db,
        brand_id=brand_id,
        user_id=current_user.id,
        action="content.preflighted",
        entity_type="preflight_report",
        entity_id=report["text_sha256"],
        details={
            "risk_level": report["risk_level"],
            "risk_score": report["risk_score"],
            "finding_count": len(report["findings"]),
            "complete": report["complete"],
        },
    )
    db.commit()
    return report
