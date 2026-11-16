
import asyncio
from io import BytesIO

from docx import Document
from fastapi import UploadFile

from app.services.document_service import extract_document_text


async def main():
    # Create a sample DOCX in memory
    document = Document()
    document.add_paragraph("BrandPilot document extraction test.")
    document.add_paragraph("This document checks brand consistency.")
    
    buffer = BytesIO()
    document.save(buffer)
    buffer.seek(0)

    upload = UploadFile(
        file=buffer,
        filename="test_document.docx"
    )

    result = await extract_document_text(upload)

    print("Filename:", result["filename"])
    print("File type:", result["file_type"])
    print("Extracted text:", result["text"])
    print("Character count:", result["character_count"])


asyncio.run(main())
