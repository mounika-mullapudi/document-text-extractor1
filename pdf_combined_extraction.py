"""Combine native text, OCR text, and tables into page-by-page results."""

import re
import traceback

import pdfplumber

from pdf_image_ocr import extract_pdf_image_text_for_page
from pdf_table_extraction import extract_pdf_tables
from pdf_text_extraction import extract_pdf_text

NATIVE_TEXT_OCR_THRESHOLD = 80


def _table_to_text(table):
    """Turn one table's rows and cells into a readable table string."""
    lines = []
    for row in table:
        cells = [
            str(cell).replace("\n", " ").strip() if cell else ""
            for cell in row
        ]
        lines.append("|" + "|".join(cells) + "|")
    return "\n".join(lines)


def _contains_text(existing_text, candidate_text):
    """Return True when candidate text already appears in existing text."""
    existing = " ".join(existing_text.casefold().split())
    candidate = " ".join(candidate_text.casefold().split())
    return bool(candidate) and candidate in existing


def _table_is_in_text(existing_text, table):
    """Return True when all non-empty table cells appear in existing text."""
    cells = [cell for row in table for cell in row if cell and cell.strip()]
    return bool(cells) and all(
        _contains_text(existing_text, cell) for cell in cells
    )


def extract_combined_pdf(pdf_path):
    """Combine the three extraction modules into five fields per page."""
    native_pages = extract_pdf_text(pdf_path)
    table_pages = extract_pdf_tables(pdf_path)

    page_results = {}
    with pdfplumber.open(pdf_path) as pdf:
        for page_number, plumber_page in enumerate(pdf.pages, start=1):
            page_id = f"PAGE_{page_number:03d}"
            print(
                f"[BEFORE COMBINE] page_id={page_id} | "
                f"pdf_page={page_number}"
            )
            try:
                native_result = native_pages[page_id]
                tables = table_pages.get(page_id, [])
            except Exception:
                print(
                    f"[AFTER COMBINE] page_id={page_id} | "
                    f"pdf_page={page_number} | error=see traceback"
                )
                traceback.print_exc()
                raise
            page_text = native_result["page_text"]
            line_format = native_result["line_format"]

            native_text = "\n".join(page_text)
            native_character_count = len(re.sub(r"\W+", "", native_text))
            image_regions = [
                (
                    image["x0"],
                    image["top"],
                    image["x1"],
                    image["bottom"],
                )
                for image in plumber_page.images
            ]

            text_from_images = []
            if native_character_count < NATIVE_TEXT_OCR_THRESHOLD:
                # Scans usually have no selectable text, so OCR the whole page.
                ocr_text = extract_pdf_image_text_for_page(
                    pdf_path, page_number
                )
                if ocr_text:
                    text_from_images.append(ocr_text)
            elif image_regions:
                # Preserve native text; OCR only embedded image regions.
                ocr_text = extract_pdf_image_text_for_page(
                    pdf_path, page_number, image_regions
                )
                if ocr_text:
                    text_from_images.append(ocr_text)

            text_from_tables = [_table_to_text(table) for table in tables]

            # Keep native text as the main content, then add table or OCR text
            # only when it is not already represented in the page content.
            page_content = list(page_text)
            combined_so_far = "\n".join(page_content)
            for table, table_text in zip(tables, text_from_tables):
                if not _table_is_in_text(combined_so_far, table):
                    page_content.append(table_text)
                    combined_so_far += "\n" + table_text

            for image_text in text_from_images:
                unique_lines = [
                    line.strip()
                    for line in image_text.splitlines()
                    if line.strip()
                    and not _contains_text(combined_so_far, line)
                ]
                if unique_lines:
                    page_content.extend(unique_lines)
                    combined_so_far += "\n" + "\n".join(unique_lines)

            page_result = {
                "page_id": page_id,
                "pdf_page": page_number,
                "page_text": page_text,
                "line_format": line_format,
                "text_from_images": text_from_images,
                "text_from_tables": text_from_tables,
                "page_content": page_content,
            }
            final_text = "\n".join(page_content)
            print(
                f"[AFTER COMBINE] page_id={page_id} | "
                f"pdf_page={page_number} | final_page={page_number} | "
                f"chars={len(final_text)} | "
                f"text_preview={final_text[:200]!r} | "
                f"empty={not bool(final_text.strip())} | error=None"
            )
            page_results[page_id] = page_result

    return page_results