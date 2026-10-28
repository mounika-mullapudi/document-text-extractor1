"""Extract selectable text and font information from each PDF page."""

from pathlib import Path
import traceback

from pdfminer.high_level import extract_pages
from pdfminer.layout import LTChar, LTTextContainer


def text_extraction(element):
    """Return a text block and its unique (font name, font size) pairs."""
    line_text = element.get_text()
    line_formats = set()

    for text_line in element:
        if isinstance(text_line, LTTextContainer):
            for character in text_line:
                if isinstance(character, LTChar):
                    line_formats.add(
                        (character.fontname, round(character.size, 2))
                    )

    return line_text, sorted(line_formats)


def extract_pdf_text(pdf_path):
    """Return each page's selectable text blocks and their font details."""
    pdf_file = Path(pdf_path)
    if not pdf_file.is_file():
        raise FileNotFoundError(f"PDF file not found: {pdf_file}")

    pages = {}
    for page_number, page in enumerate(extract_pages(str(pdf_file)), start=1):
        page_id = f"PAGE_{page_number:03d}"
        page_text = []
        line_format = []
        print(
            f"[BEFORE NATIVE TEXT] page_id={page_id} | "
            f"pdf_page={page_number} | method=native text"
        )
        try:
            for element in page:
                if isinstance(element, LTTextContainer):
                    text, formats = text_extraction(element)
                    if text.strip():
                        page_text.append(text)
                        line_format.append(formats)
        except Exception:
            print(
                f"[AFTER NATIVE TEXT] page_id={page_id} | "
                f"pdf_page={page_number} | method=native text | "
                "chars=0 | text_preview='' | empty=True | error=see traceback"
            )
            traceback.print_exc()
            raise

        extracted_text = "".join(page_text)
        print(
            f"[AFTER NATIVE TEXT] page_id={page_id} | "
            f"pdf_page={page_number} | method=native text | "
            f"chars={len(extracted_text)} | "
            f"text_preview={extracted_text[:200]!r} | "
            f"empty={not bool(extracted_text.strip())} | error=None"
        )
        pages[page_id] = {
            "pdf_page": page_number,
            "page_text": page_text,
            "line_format": line_format,
        }

    return pages