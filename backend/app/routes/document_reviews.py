from __future__ import annotations

import io
from pathlib import Path
from uuid import UUID
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.brand_rule import BrandRule
from app.models.review import ContentReview
from app.models.review_decision import ReviewDecision
from app.models.user import User
from app.services.audit_service import create_audit_log
from app.services.brand_access import authorize_brand_action
from app.services.review_service import review_content_with_fallback

router = APIRouter(tags=["Document Reviews"])
MAX_FILE_BYTES = 10 * 1024 * 1024


def extract_document(filename: str, raw: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    try:
        if suffix == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw))
            if reader.is_encrypted:
                raise ValueError("Password-protected PDFs are not supported.")
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        elif suffix == ".docx":
            from docx import Document
            document = Document(io.BytesIO(raw))
            parts = [p.text for p in document.paragraphs if p.text.strip()]
            for table in document.tables:
                for row in table.rows:
                    parts.append(" | ".join(cell.text for cell in row.cells))
            text = "\n".join(parts)
        else:
            raise ValueError("Only PDF and DOCX files are supported.")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Could not read this document. Check that it is a valid, uncorrupted PDF or DOCX.") from exc
    text = text.strip()
    if not text:
        raise ValueError("No selectable text was found. Scanned/image-only PDFs require OCR and are not supported.")
    if len(text) > 100_000:
        raise ValueError("Extracted document text exceeds the 100,000 character limit.")
    return text


@router.post("/brands/{brand_id}/documents/review", status_code=status.HTTP_201_CREATED)
async def review_document(
    brand_id: UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    authorize_brand_action(db, current_user.id, brand_id, "brand:read")
    filename = Path(file.filename or "document").name
    if Path(filename).suffix.lower() not in {".pdf", ".docx"}:
        raise HTTPException(status_code=415, detail="Upload a PDF or DOCX file.")
    raw = await file.read(MAX_FILE_BYTES + 1)
    if not raw or len(raw) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="File must be non-empty and no larger than 10 MB.")
    try:
        content = extract_document(filename, raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    rules = db.scalars(select(BrandRule).where(
        BrandRule.brand_id == brand_id, BrandRule.is_active.is_(True)
    )).all()
    brand_rules = [{"category": r.category, "title": r.title,
                    "description": r.description, "severity": r.severity}
                   for r in rules]
    try:
        result, provider = review_content_with_fallback(content, brand_rules)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    review = ContentReview(
        brand_id=brand_id, user_id=current_user.id, content=content,
        provider=provider, overall_status=result.overall_status,
        overall_score=result.overall_score, summary=result.summary,
        findings=[f.model_dump() for f in result.findings],
    )
    db.add(review)
    db.flush()
    create_audit_log(
        db=db, brand_id=brand_id, user_id=current_user.id,
        action="document.reviewed", entity_type="content_review",
        entity_id=str(review.id),
        details={"filename": filename, "provider": provider,
                 "overall_status": review.overall_status,
                 "overall_score": review.overall_score,
                 "character_count": len(content)},
    )
    db.commit()
    db.refresh(review)
    return {
        "review_id": str(review.id), "filename": filename,
        "character_count": len(content), "provider": provider,
        "overall_status": review.overall_status,
        "overall_score": review.overall_score, "summary": review.summary,
        "findings": review.findings,
        "message": "Document extracted and reviewed. Resolve every finding before exporting.",
    }


@router.get("/documents/reviews/{review_id}/approved-export")
def export_approved_document(
    review_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    review = db.get(ContentReview, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found.")
    authorize_brand_action(db, current_user.id, review.brand_id, "reviews:decide")
    decisions = db.scalars(select(ReviewDecision).where(
        ReviewDecision.review_id == review_id
    )).all()
    by_index = {d.finding_index: d for d in decisions}
    unresolved = [i for i in range(len(review.findings)) if i not in by_index]
    if unresolved:
        raise HTTPException(
            status_code=409,
            detail=f"{len(unresolved)} finding(s) still need an accept or override decision.",
        )

    approved_text = review.content
    replacements = []
    for index, finding in enumerate(review.findings):
        decision = by_index[index]
        if decision.decision == "accepted" and decision.replacement_text:
            original = finding.get("original_text", "")
            if original:
                replacements.append((original, decision.replacement_text))
    for original, replacement in sorted(replacements, key=lambda x: len(x[0]), reverse=True):
        approved_text = approved_text.replace(original, replacement)

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    story = [
        Paragraph("BRANDPILOT - APPROVED CONTENT", styles["Title"]),
        Paragraph("Approved export generated after all review findings received a recorded decision.", styles["Italic"]),
        Spacer(1, 14),
        Paragraph(f"Review ID: {escape(str(review.id))}", styles["Normal"]),
        Paragraph(f"Status: {escape(review.overall_status)} | Score: {review.overall_score}/100", styles["Normal"]),
        Spacer(1, 14),
    ]
    for paragraph in approved_text.splitlines():
        if paragraph.strip():
            story.append(Paragraph(escape(paragraph), styles["BodyText"]))
            story.append(Spacer(1, 6))
    story.extend([Spacer(1, 18), Paragraph("BRANDPILOT APPROVED EXPORT", styles["Heading2"])])
    SimpleDocTemplate(buffer, pagesize=A4, title="BrandPilot Approved Export").build(story)
    buffer.seek(0)
    create_audit_log(
        db=db, brand_id=review.brand_id, user_id=current_user.id,
        action="document.approved_exported", entity_type="content_review",
        entity_id=str(review.id),
        details={"review_id": str(review.id), "decision_count": len(by_index)},
    )
    db.commit()
    return StreamingResponse(
        buffer, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="brandpilot-approved-{review.id}.pdf"'},
    )
