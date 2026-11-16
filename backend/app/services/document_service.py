
import io
from pathlib import Path

from docx import Document as WordDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas


MAX_FILE_SIZE = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".docx"}


def extract_document_text(file_data: bytes, filename: str) -> dict:
    extension = Path(filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Only PDF and DOCX files are supported.")

    if not file_data:
        raise ValueError("The uploaded file is empty.")

    if len(file_data) > MAX_FILE_SIZE:
        raise ValueError("File size exceeds the 10 MB limit.")

    if extension == ".pdf":
        reader = PdfReader(io.BytesIO(file_data))

        if reader.is_encrypted:
            raise ValueError("Encrypted PDFs are not supported.")

        text = "\n".join(
            page.extract_text() or ""
            for page in reader.pages
        )

    else:
        document = WordDocument(io.BytesIO(file_data))

        paragraphs = [
            paragraph.text
            for paragraph in document.paragraphs
            if paragraph.text.strip()
        ]

        tables = []
        for table in document.tables:
            for row in table.rows:
                tables.append(
                    " | ".join(cell.text for cell in row.cells)
                )

        text = "\n".join(paragraphs + tables)

    text = text.strip()

    if not text:
        raise ValueError(
            "No readable text found. Scanned PDFs require OCR."
        )

    return {
        "filename": Path(filename).name,
        "file_type": extension.lstrip("."),
        "text": text,
        "character_count": len(text),
    }


def apply_docx_decisions(
    file_data: bytes,
    findings: list[dict],
    decisions: list,
) -> bytes:
    """Apply accepted finding replacements to a copy of the original DOCX."""

    document = WordDocument(io.BytesIO(file_data))

    accepted = {
        decision.finding_index: decision.replacement_text
        for decision in decisions
        if decision.decision == "accepted"
        and decision.replacement_text
    }

    def iter_paragraphs(doc):
        for paragraph in doc.paragraphs:
            yield paragraph

        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    yield from cell.paragraphs

    paragraphs = list(iter_paragraphs(document))

    for finding_index, replacement in accepted.items():
        if finding_index < 0 or finding_index >= len(findings):
            raise ValueError(
                f"Invalid finding index: {finding_index}"
            )

        original = findings[finding_index].get("original_text", "")

        if not original:
            raise ValueError(
                f"Finding {finding_index} has no original text."
            )

        matches = [
            paragraph
            for paragraph in paragraphs
            if original in paragraph.text
        ]

        total_matches = sum(
            paragraph.text.count(original)
            for paragraph in matches
        )

        if total_matches != 1:
            raise ValueError(
                f"Cannot safely apply finding {finding_index}: "
                f"expected one exact match, found {total_matches}."
            )

        paragraph = matches[0]
        combined = "".join(run.text for run in paragraph.runs)
        start = combined.index(original)
        end = start + len(original)

        # Map the replacement across existing runs, retaining the
        # formatting of the first affected run.
        position = 0
        affected = []

        for run in paragraph.runs:
            run_start = position
            run_end = position + len(run.text)

            if run_end > start and run_start < end:
                affected.append((run, run_start, run_end))

            position = run_end

        if not affected:
            raise ValueError(
                f"Could not locate the text for finding {finding_index}."
            )

        first_run, first_start, _ = affected[0]
        last_run, _, last_end = affected[-1]

        prefix = first_run.text[:start - first_start]
        suffix = last_run.text[end - (last_end - len(last_run.text)):]

        if first_run is last_run:
            first_run.text = prefix + replacement + suffix
        else:
            first_run.text = prefix + replacement

            for run, _, _ in affected[1:-1]:
                run.text = ""

            last_run.text = suffix

    output = io.BytesIO()
    document.save(output)
    return output.getvalue()

def stamp_approved_document(
    file_data: bytes,
    file_type: str,
    approved_by: str,
    approved_at: str,
) -> bytes:
    """Return a stamped copy without modifying the stored original."""

    if file_type == "pdf":
        reader = PdfReader(io.BytesIO(file_data))
        writer = PdfWriter()

        for page in reader.pages:
            packet = io.BytesIO()
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)

            stamp = canvas.Canvas(packet, pagesize=(width, height))
            stamp.saveState()
            stamp.setFillColorRGB(0.05, 0.48, 0.25)
            stamp.setFont("Helvetica-Bold", 25)
            stamp.drawCentredString(
                width / 2,
                height - 45,
                "APPROVED",
            )
            stamp.setFont("Helvetica", 8)
            stamp.drawCentredString(
                width / 2,
                25,
                f"Approved by {approved_by} | {approved_at}",
            )
            stamp.restoreState()
            stamp.save()

            packet.seek(0)
            overlay = PdfReader(packet).pages[0]
            page.merge_page(overlay)
            writer.add_page(page)

        output = io.BytesIO()
        writer.write(output)
        return output.getvalue()

    if file_type == "docx":
        document = WordDocument(io.BytesIO(file_data))

        for section in document.sections:
            header = section.header
            paragraph = header.paragraphs[0]
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER

            run = paragraph.add_run("APPROVED")
            run.bold = True
            run.font.size = Pt(20)
            run.font.color.rgb = RGBColor(0, 128, 64)

            footer = section.footer
            footer_paragraph = footer.paragraphs[0]
            footer_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER

            footer_paragraph.add_run(
                f"Approved by {approved_by} | {approved_at}"
            )

        output = io.BytesIO()
        document.save(output)
        return output.getvalue()

    raise ValueError("Unsupported document format.")
