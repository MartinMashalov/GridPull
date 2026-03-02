import fitz  # PyMuPDF
import os
from typing import List


def read_pdf_text(file_path: str) -> dict:
    """Read PDF and extract text content page by page."""
    doc = fitz.open(file_path)
    pages = []
    full_text = ""

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text")
        pages.append({
            "page": page_num + 1,
            "text": text.strip(),
        })
        full_text += f"\n--- Page {page_num + 1} ---\n{text}"

    doc.close()
    return {
        "page_count": len(pages),
        "pages": pages,
        "full_text": full_text.strip(),
    }


def get_pdf_page_count(file_path: str) -> int:
    """Get number of pages in PDF."""
    doc = fitz.open(file_path)
    count = len(doc)
    doc.close()
    return count
