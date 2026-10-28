"""Extract digital tables from PDF pages with pdfplumber."""

from pathlib import Path

import pdfplumber


def extract_pdf_tables(pdf_path):
    """Return the tables found on each page as lists of rows and cells."""
    pdf_file = Path(pdf_path)
    if not pdf_file.is_file():
        raise FileNotFoundError(f"PDF file not found: {pdf_file}")

    tables_by_page = {}
    with pdfplumber.open(pdf_file) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables() or []
            tables_by_page[f"Page_{page_number}"] = tables

    return tables_by_page