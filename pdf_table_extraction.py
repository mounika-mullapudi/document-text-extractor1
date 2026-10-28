"""Extract digital tables from PDF pages with pdfplumber."""

from pathlib import Path
import traceback

import pdfplumber


def extract_pdf_tables(pdf_path):
    """Return the tables found on each page as lists of rows and cells."""
    pdf_file = Path(pdf_path)
    if not pdf_file.is_file():
        raise FileNotFoundError(f"PDF file not found: {pdf_file}")

    tables_by_page = {}
    with pdfplumber.open(pdf_file) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            page_id = f"PAGE_{page_number:03d}"
            print(
                f"[BEFORE TABLE] page_id={page_id} | "
                f"pdf_page={page_number} | method=table extraction"
            )
            try:
                tables = page.extract_tables() or []
            except Exception:
                print(
                    f"[AFTER TABLE] page_id={page_id} | "
                    f"pdf_page={page_number} | method=table extraction | "
                    "chars=0 | text_preview='' | empty=True | error=see traceback"
                )
                traceback.print_exc()
                raise

            extracted_text = "\n".join(
                " | ".join(str(cell or "") for cell in row)
                for table in tables
                for row in table
            )
            print(
                f"[AFTER TABLE] page_id={page_id} | "
                f"pdf_page={page_number} | method=table extraction | "
                f"chars={len(extracted_text)} | "
                f"text_preview={extracted_text[:200]!r} | "
                f"empty={not bool(extracted_text.strip())} | error=None"
            )
            tables_by_page[page_id] = tables

    return tables_by_page