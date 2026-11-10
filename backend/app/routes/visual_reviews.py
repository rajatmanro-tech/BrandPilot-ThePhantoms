import json
import os
import tempfile
from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.visual_review import VisualReview
from app.schemas.visual_review import VisualReviewResponse
from app.services.brand_access import authorize_brand_action
from app.services.audit_service import create_audit_log
from app.services.visual_review import BrandKit, review_image

router = APIRouter(tags=["Image Reviews"])
MAX_IMAGE_BYTES = 10 * 1024 * 1024


@router.post("/brands/{brand_id}/image-reviews", response_model=VisualReviewResponse, status_code=201)
async def create_image_review(
    brand_id: UUID,
    image: UploadFile = File(...),
    palette: str = Form(..., description='JSON object, e.g. {"primary":"#123456","paper":"#FFFFFF"}'),
    text_ink: str = Form(default="#000000"),
    wordmark_colors: str = Form(default='["#000000","#FFFFFF"]'),
    alt_text: str | None = Form(default=None),
    contrast_min: float = Form(default=4.5, ge=1, le=21),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    authorize_brand_action(db, current_user.id, brand_id, "brand:read")

    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="Upload a supported image file.")

    raw = await image.read()

    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image must be between 1 byte and 10 MB.")

    try:
        # Parse palette JSON
        try:
            palette_data = json.loads(palette)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid palette JSON: {exc}") from exc

        # Accept either JSON array or comma-separated colours
        try:
            wordmark_data = json.loads(wordmark_colors)
        except json.JSONDecodeError:
            wordmark_data = [
                color.strip()
                for color in wordmark_colors.split(",")
                if color.strip()
            ]

        if not isinstance(palette_data, dict) or not palette_data:
            raise ValueError("Palette must be a non-empty JSON object.")

        if not all(
            isinstance(k, str)
            and isinstance(v, str)
            and len(v) == 7
            and v.startswith("#")
            for k, v in palette_data.items()
        ):
            raise ValueError("Palette values must be #RRGGBB hex colours.")

        if not isinstance(wordmark_data, list) or not all(
            isinstance(v, str)
            and len(v) == 7
            and v.startswith("#")
            for v in wordmark_data
        ):
            raise ValueError("wordmark_colors must contain valid #RRGGBB hex colours.")

        kit = BrandKit(
            palette=palette_data,
            wordmark_colors=wordmark_data,
            text_ink=text_ink,
            contrast_min=contrast_min,
            logo_template_path=None,
        )

        img = Image.open(BytesIO(raw))
        img.verify()

        # Reopen after verify because verify() consumes the image stream
        img = Image.open(BytesIO(raw))
        report = review_image(img, kit, alt_text=alt_text)

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid visual review configuration: {exc}"
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not process image: {exc}"
        ) from exc

    record = VisualReview(
        brand_id=brand_id,
        user_id=current_user.id,
        filename=os.path.basename(image.filename or "creative"),
        report=report,
    )

    db.add(record)
    db.flush()

    create_audit_log(
        db=db,
        brand_id=brand_id,
        user_id=current_user.id,
        action="creative.image_reviewed",
        entity_type="visual_review",
        entity_id=str(record.id),
        details={
            "filename": record.filename,
            "finding_count": len(report.get("findings", [])),
            "max_severity": report.get("max_severity"),
            "degraded_checks": report.get("degraded_checks", []),
        },
    )

    db.commit()
    db.refresh(record)

    return record


@router.get("/brands/{brand_id}/image-reviews", response_model=list[VisualReviewResponse])
def get_image_reviews(
    brand_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    authorize_brand_action(db, current_user.id, brand_id, "brand:read")
    return db.scalars(
        select(VisualReview)
        .where(VisualReview.brand_id == brand_id)
        .order_by(VisualReview.created_at.desc())
    ).all()
