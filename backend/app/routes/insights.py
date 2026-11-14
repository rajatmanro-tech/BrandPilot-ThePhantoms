
from collections import Counter
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.review import ContentReview
from app.models.review_decision import ReviewDecision
from app.models.user import User
from app.services.brand_access import authorize_brand_action

router = APIRouter(tags=["Insights"])


@router.get("/brands/{brand_id}/insights")
def get_brand_insights(
    brand_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    authorize_brand_action(
        db, current_user.id, brand_id, "reports:read"
    )

    reviews = db.scalars(
        select(ContentReview)
        .where(ContentReview.brand_id == brand_id)
        .order_by(ContentReview.created_at.desc())
    ).all()

    decisions = db.scalars(
        select(ReviewDecision)
        .join(
            ContentReview,
            ReviewDecision.review_id == ContentReview.id,
        )
        .where(ContentReview.brand_id == brand_id)
    ).all()

    total = len(reviews)
    passed = sum(r.overall_status == "pass" for r in reviews)
    needs_changes = sum(
        r.overall_status == "needs_changes" for r in reviews
    )
    failed = sum(r.overall_status == "fail" for r in reviews)

    average_score = (
        round(sum(r.overall_score for r in reviews) / total, 1)
        if total else None
    )

    issue_counts = Counter()
    override_counts = Counter()
    decision_counts = Counter(
        decision.decision for decision in decisions
    )

    review_lookup = {review.id: review for review in reviews}

    for review in reviews:
        for finding in review.findings or []:
            category = finding.get("category", "Other")
            issue = finding.get("issue", "Unspecified issue")
            issue_counts[(category, issue)] += 1

    for decision in decisions:
        if decision.decision != "overridden":
            continue

        review = review_lookup.get(decision.review_id)
        if not review:
            continue

        findings = review.findings or []

        if decision.finding_index >= len(findings):
            continue

        finding = findings[decision.finding_index]
        category = finding.get("category", "Other")
        issue = finding.get("issue", "Unspecified issue")

        override_counts[(category, issue)] += 1

    top_issues = [
        {
            "category": category,
            "issue": issue,
            "count": count,
        }
        for (category, issue), count in issue_counts.most_common(10)
    ]

    ambiguity_signals = [
        {
            "category": category,
            "issue": issue,
            "override_count": count,
            "signal": "Repeated overrides; review the related guideline.",
        }
        for (category, issue), count in override_counts.most_common(10)
        if count >= 2
    ]

    return {
        "total_reviews": total,
        "passed": passed,
        "needs_changes": needs_changes,
        "failed": failed,
        "average_score": average_score,
        "accepted_decisions": decision_counts.get("accepted", 0),
        "overridden_decisions": decision_counts.get("overridden", 0),
        "top_issues": top_issues,
        "ambiguity_signals": ambiguity_signals,
        "ambiguity_note": (
            "Repeated overrides are indicators for manual guideline review, "
            "not proof that a guideline is ambiguous."
        ),
    }
