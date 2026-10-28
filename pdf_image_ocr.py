"""Convert PDF pages to images and read their text with OCR."""

import os
import shutil
import traceback
from pathlib import Path

import pytesseract
from pdf2image import convert_from_path
from PIL import Image
from PyPDF2 import PdfReader


def configure_tesseract():
    """Point pytesseract to an installed Tesseract executable."""
    candidates = [
        os.environ.get("TESSERACT_CMD"),
        shutil.which("tesseract"),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    ]

    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            pytesseract.pytesseract.tesseract_cmd = candidate
            return

    raise FileNotFoundError(
        "Tesseract was not found. Set the TESSERACT_CMD environment variable."
    )


def extract_pdf_image_text(pdf_path):
    """Return OCR text for each PDF page, rendered and processed separately."""
    pdf_file = Path(pdf_path)
    if not pdf_file.is_file():
        raise FileNotFoundError(f"PDF file not found: {pdf_file}")

    page_count = len(PdfReader(str(pdf_file)).pages)
    page_text = {}
    for page_number in range(1, page_count + 1):
        page_id = f"PAGE_{page_number:03d}"
        page_text[page_id] = extract_pdf_image_text_for_page(
            pdf_file, page_number
        )
    return page_text


def extract_pdf_image_text_for_page(pdf_path, page_number=1, image_regions=None):
    """OCR one page, optionally limiting OCR to its embedded image regions.

    Each image region is a (left, top, right, bottom) tuple in PDF points.
    """
    pdf_file = Path(pdf_path)
    if not pdf_file.is_file():
        raise FileNotFoundError(f"PDF file not found: {pdf_file}")

    configure_tesseract()
    page_count = len(PdfReader(str(pdf_file)).pages)
    if page_number < 1 or page_number > page_count:
        raise ValueError(f"Page number must be between 1 and {page_count}.")

    poppler_path = os.environ.get("POPPLER_PATH")
    page_id = f"PAGE_{page_number:03d}"
    print(
        f"[BEFORE OCR] page_id={page_id} | pdf_page={page_number} | "
        "method=OCR | image_size=unknown | image_created=False"
    )
    try:
        page_images = convert_from_path(
            str(pdf_file),
            first_page=page_number,
            last_page=page_number,
            dpi=300,
            poppler_path=poppler_path,
        )
        if not page_images:
            raise RuntimeError(f"Could not render PDF page {page_number}.")

        page_image: Image.Image = page_images[0].convert("RGB")
    except Exception:
        print(
            f"[AFTER OCR] page_id={page_id} | pdf_page={page_number} | "
            "method=OCR | chars=0 | text_preview='' | empty=True | "
            "image_created=False | error=see traceback"
        )
        traceback.print_exc()
        raise

    print(
        f"[BEFORE OCR] page_id={page_id} | pdf_page={page_number} | "
        f"method=OCR | image_size={page_image.width}x{page_image.height} | "
        "image_created=True"
    )
    if image_regions is None:
        image_regions = [(0, 0, page_image.width, page_image.height)]
        page_width = page_image.width
        page_height = page_image.height
    else:
        page_box = PdfReader(str(pdf_file)).pages[page_number - 1].mediabox
        page_width = float(page_box.width)
        page_height = float(page_box.height)

    page_text = []
    try:
        for left, top, right, bottom in image_regions:
            pixel_left = left * page_image.width / page_width
            pixel_top = top * page_image.height / page_height
            pixel_right = right * page_image.width / page_width
            pixel_bottom = bottom * page_image.height / page_height
            crop = page_image.crop((
                max(0, int(pixel_left)),
                max(0, int(pixel_top)),
                min(page_image.width, int(pixel_right)),
                min(page_image.height, int(pixel_bottom)),
            ))
            if crop.width and crop.height:
                text = pytesseract.image_to_string(crop, lang="eng").strip()
                if text:
                    page_text.append(text)
    except Exception:
        print(
            f"[AFTER OCR] page_id={page_id} | pdf_page={page_number} | "
            "method=OCR | chars=0 | text_preview='' | empty=True | "
            f"image_created=True | image_size={page_image.width}x{page_image.height} | "
            "error=see traceback"
        )
        traceback.print_exc()
        raise

    extracted_text = "\n".join(page_text)
    print(
        f"[AFTER OCR] page_id={page_id} | pdf_page={page_number} | "
        f"method=OCR | chars={len(extracted_text)} | "
        f"text_preview={extracted_text[:200]!r} | "
        f"empty={not bool(extracted_text.strip())} | error=None"
    )
    return extracted_text