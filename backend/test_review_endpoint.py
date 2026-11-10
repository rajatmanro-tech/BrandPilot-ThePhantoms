
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.core.dependencies import get_current_user
from app.db.session import SessionLocal, get_db
from app.models.user import User
from app.models.brand import Brand
from app.models.membership import BrandMembership
from app.models.review import ContentReview
from app.services.gemini_service import GeminiReviewResult
from app.models.audit_log import AuditLog

BRAND_ID = "858096d8-8511-4119-b6fb-e37cbb716d3a"


def test_content_review_endpoint():
    db = SessionLocal()

    try:
        brand = db.get(Brand, BRAND_ID)

        assert brand is not None, "Test brand not found."

        membership = db.scalar(
            select(BrandMembership).where(
                BrandMembership.brand_id == brand.id
            )
        )

        assert membership is not None, "No brand membership found."

        user = db.get(User, membership.user_id)

        assert user is not None, "Test user not found."

        def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: user

        mock_result = GeminiReviewResult(
            overall_status="needs_changes",
            overall_score=45,
            summary="The content violates the professional tone rule.",
            findings=[
                {
                    "category": "Tone of Voice",
                    "severity": "high",
                    "issue": "Unprofessional language",
                    "explanation": "The content uses exaggerated claims and informal language.",
                    "suggestion": "Use clear and professional language.",
                    "original_text": "YO GUYS!!!",
                }
            ],
        )

        with patch(
            "app.routes.reviews.review_content_with_fallback",
            return_value=(mock_result, "mock"),
        ):
            client = TestClient(app)

            response = client.post(
                f"/brands/{BRAND_ID}/reviews",
                json={
                    "content": "YO GUYS!!! Our product is the BEST."
                },
            )

        print("HTTP status:", response.status_code)
        print("Response:", response.json())

        assert response.status_code == 201

        review_id = response.json()["id"]

        saved_review = db.get(ContentReview, review_id)

        assert saved_review is not None
        assert saved_review.provider == "mock"
        assert saved_review.overall_score == 45
        assert len(saved_review.findings) == 1

        print("PASSED: Review was successfully saved in PostgreSQL.")

        audit_entry = db.scalar(
            select(AuditLog).where(
                AuditLog.entity_id == str(saved_review.id),
                AuditLog.action == "content.reviewed",
            )
        )

        assert audit_entry is not None, "Audit event was not created!"

        print("PASSED: Review audit event was saved.")

        db.delete(audit_entry)
        db.delete(saved_review)
        db.commit()

        print("Test review and audit event cleaned up.")

    finally:
        app.dependency_overrides.clear()
        db.close()


if __name__ == "__main__":
    test_content_review_endpoint()
