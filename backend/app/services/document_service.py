
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

        page_texts = [
            page.extract_text() or ""
            for page in reader.pages
        ]

        text = "\n".join(
            f"[PAGE {index + 1}]\n{page_text}"
            for index, page_text in enumerate(page_texts)
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
    """Apply accepted replacements while tolerating DOCX whitespace differences."""

    import re

    document = WordDocument(io.BytesIO(file_data))

    accepted = {
        decision.finding_index: decision.replacement_text
        for decision in decisions
        if decision.decision == "accepted" and decision.replacement_text
    }

    def iter_paragraphs(doc):
        for paragraph in doc.paragraphs:
            yield paragraph

        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    yield from cell.paragraphs

    def normalized_with_positions(text):
        chars = []
        starts = []
        ends = []

        for i, char in enumerate(text):
            if char.isspace():
                if chars and chars[-1] == " ":
                    ends[-1] = i + 1
                    continue
                char = " "

            chars.append(char)
            starts.append(i)
            ends.append(i + 1)

        return "".join(chars).strip(), starts, ends

    paragraphs = list(iter_paragraphs(document))

    for finding_index, replacement in accepted.items():
        if not 0 <= finding_index < len(findings):
            raise ValueError(f"Invalid finding index: {finding_index}")

        original = findings[finding_index].get("original_text", "")

        if not original:
            raise ValueError(f"Finding {finding_index} has no original text.")

        target = re.sub(r"\s+", " ", original).strip()
        matches = []

        for paragraph in paragraphs:
            combined = "".join(run.text for run in paragraph.runs)
            normalized, starts, ends = normalized_with_positions(combined)

            position = normalized.find(target)

            while position != -1:
                actual_start = starts[position]
                actual_end = ends[position + len(target) - 1]
                matches.append((paragraph, actual_start, actual_end))
                position = normalized.find(target, position + 1)

        if len(matches) != 1:
            raise ValueError(
                f"Cannot safely apply finding {finding_index}: "
                f"expected one normalized match, found {len(matches)}. "
                "The original text may span multiple paragraphs."
            )

        paragraph, start, end = matches[0]

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
                f"Could not locate finding {finding_index} in DOCX runs."
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




def apply_pdf_decisions(
    file_data: bytes,
    findings: list[dict],
    decisions: list,
) -> bytes:
    """Apply accepted PDF replacements using surrounding context."""
    import re
    import fitz

    accepted = {
        decision.finding_index: decision.replacement_text
        for decision in decisions
        if decision.decision == "accepted"
        and decision.replacement_text
    }

    def normalize(text):
        return re.sub(r"\s+", " ", text).strip()

    pdf = fitz.open(stream=file_data, filetype="pdf")

    try:
        # Collect matches before editing so page text positions
        # are not affected by earlier replacements.
        replacements = []

        for finding_index, replacement in accepted.items():
            if not 0 <= finding_index < len(findings):
                raise ValueError(
                    f"Invalid finding index: {finding_index}"
                )

            finding = findings[finding_index]

            original = normalize(finding.get("original_text", ""))
            before = normalize(finding.get("context_before") or "")
            after = normalize(finding.get("context_after") or "")

            if not original:
                raise ValueError(
                    f"Finding {finding_index} has no original text."
                )

            candidates = []

            for page_number, page in enumerate(pdf):
                page_text = normalize(page.get_text("text"))

                search_start = 0
                while True:
                    position = page_text.find(original, search_start)

                    if position == -1:
                        break

                    preceding = page_text[:position]
                    following = page_text[position + len(original):]

                    before_ok = (
                        not before
                        or preceding.endswith(before)
                    )
                    after_ok = (
                        not after
                        or following.startswith(after)
                    )

                    if before_ok and after_ok:
                        candidates.append(page_number)

                    search_start = position + 1

            if len(candidates) != 1:
                raise ValueError(
                    f"Cannot safely identify PDF finding {finding_index}: "
                    f"found {len(candidates)} context matches."
                )

            page_number = candidates[0]
            page = pdf[page_number]
            rects = page.search_for(
                finding.get("original_text", "").strip()
            )

            if len(rects) != 1:
                raise ValueError(
                    f"Cannot safely locate PDF finding {finding_index} "
                    "on its identified page."
                )

            replacements.append(
                (page_number, rects[0], replacement, finding_index)
            )

        # Apply replacements after all findings have been validated.
        for page_number, rect, replacement, finding_index in replacements:
            page = pdf[page_number]

            expanded_rect = fitz.Rect(
                rect.x0,
                max(0, rect.y0 - 2),
                min(page.rect.width - 35, rect.x0 + 350),
                min(page.rect.height - 35, rect.y1 + 55),
            )

            page.add_redact_annot(rect, fill=(1, 1, 1))
            page.apply_redactions()

            result = page.insert_textbox(
                expanded_rect,
                replacement,
                fontsize=9,
                fontname="helv",
                color=(0, 0, 0),
                align=0,
            )

            if result < 0:
                raise ValueError(
                    f"Replacement for finding {finding_index} "
                    "does not fit in the available PDF area."
                )

        return pdf.tobytes()

    finally:
        pdf.close()



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
