
import os
import glob
import hashlib
import re
import shutil
from pathlib import Path

import pdfplumber
import pytesseract
from PIL import Image, ImageFilter
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer, LTChar
from pdf2image import convert_from_path
from pytesseract import Output


def configure_tesseract():
    """Use an explicitly configured or commonly installed Tesseract binary."""
    configured_path = os.environ.get("TESSERACT_CMD")
    candidates = [
        configured_path,
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        shutil.which("tesseract"),
    ]

    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            pytesseract.pytesseract.tesseract_cmd = candidate
            return candidate

    return None


def find_poppler_bin():
    configured_path = os.environ.get("POPPLER_PATH")
    if configured_path and Path(configured_path).is_dir():
        return configured_path

    executable = shutil.which("pdftoppm")
    if executable:
        return str(Path(executable).parent)

    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None

    pattern = os.path.join(
        local_app_data,
        "Microsoft",
        "WinGet",
        "Packages",
        "oschwartz10612.Poppler*",
        "*",
        "Library",
        "bin",
    )

    matches = sorted(glob.glob(pattern))
    return matches[-1] if matches else None


def extract_text_and_format(element):
    text = element.get_text()
    formats = set()

    for text_line in element:
        if not isinstance(text_line, LTTextContainer):
            continue

        for character in text_line:
            if isinstance(character, LTChar):
                formats.add(
                    (character.fontname, round(character.size, 2))
                )

    return text, sorted(formats)


def convert_table_to_text(table):
    lines = []

    for row in table:
        cleaned_row = [
            str(cell).replace("\n", " ").strip()
            if cell is not None
            else ""
            for cell in row
        ]
        lines.append("|" + "|".join(cleaned_row) + "|")

    return "\n".join(lines)


def _image_coverage(page):
    page_area = page.width * page.height
    image_area = sum(
        max(0, image["x1"] - image["x0"])
        * max(0, image["bottom"] - image["top"])
        for image in page.images
    )
    return min(image_area / page_area, 1) if page_area else 0


def _crop_page_image(page_image, page, image_region):
    """Crop a pdfplumber image region from its rendered page image."""
    scale_x = page_image.width / page.width
    scale_y = page_image.height / page.height
    left = max(0, int(image_region["x0"] * scale_x))
    top = max(0, int(image_region["top"] * scale_y))
    right = min(page_image.width, int(image_region["x1"] * scale_x))
    bottom = min(page_image.height, int(image_region["bottom"] * scale_y))

    # A small border helps OCR retain labels close to image edges.
    margin_x = max(2, int((right - left) * 0.02))
    margin_y = max(2, int((bottom - top) * 0.02))
    return page_image.crop((
        max(0, left - margin_x),
        max(0, top - margin_y),
        min(page_image.width, right + margin_x),
        min(page_image.height, bottom + margin_y),
    ))


def _read_ocr(image, page_mode):
    """OCR an image and return its text and mean word confidence."""
    data = pytesseract.image_to_data(
        image,
        lang="eng",
        config=f"--psm {page_mode}",
        output_type=Output.DICT,
    )
    lines = {}
    confidences = []

    for index, word in enumerate(data["text"]):
        word = word.strip()
        if not word:
            continue

        line_key = (
            data["block_num"][index],
            data["par_num"][index],
            data["line_num"][index],
        )
        lines.setdefault(line_key, []).append(word)

        try:
            confidence = float(data["conf"][index])
            if confidence >= 0:
                confidences.append(confidence)
        except (TypeError, ValueError):
            continue

    text = "\n".join(" ".join(words) for words in lines.values())
    mean_confidence = (
        sum(confidences) / len(confidences) if confidences else 0.0
    )
    return text.strip(), mean_confidence


def _correct_image_orientation(image):
    """Use Tesseract orientation detection when the scan has enough text."""
    try:
        orientation = pytesseract.image_to_osd(
            image, lang="eng", output_type=Output.DICT
        )
        rotation = int(orientation.get("rotate", 0))
        if rotation:
            return image.rotate(-rotation, expand=True)
    except (pytesseract.TesseractError, ValueError, KeyError):
        # Sparse charts and short pages may not contain enough text for OSD.
        pass
    return image


def _remove_duplicate_ocr_lines(ocr_text, existing_text):
    """Drop OCR lines already present in native text or extracted tables."""
    normalize = lambda value: re.sub(r"\W+", "", value.casefold())
    existing = normalize(existing_text)
    seen = set()
    unique_lines = []

    for line in ocr_text.splitlines():
        line = line.strip()
        normalized = normalize(line)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        if len(normalized) >= 4 and normalized in existing:
            continue
        unique_lines.append(line)

    return "\n".join(unique_lines)


def extract_combined_pdf(pdf_path):
    """Extract each page using the article's combined PDF workflow."""
    pdf_file = Path(pdf_path)

    if not pdf_file.is_file():
        raise FileNotFoundError(f"PDF file not found: {pdf_file}")

    poppler_path = find_poppler_bin()
    if not poppler_path:
        raise FileNotFoundError("Poppler was not found. Set POPPLER_PATH.")

    if not configure_tesseract():
        raise FileNotFoundError("Tesseract was not found. Set TESSERACT_CMD.")

    page_results = {}
    warnings = []
    rendered_page_hashes = {}
    with pdfplumber.open(pdf_file) as pdf:
        layouts = extract_pages(str(pdf_file))

        for page_number, layout in enumerate(layouts, start=1):
            page_text = []
            line_format = []

            # First read selectable text and font formatting with pdfminer.
            for element in layout:
                if isinstance(element, LTTextContainer):
                    text, formats = extract_text_and_format(element)
                    if text.strip():
                        page_text.append(text)
                        line_format.append(formats)

            plumber_page = pdf.pages[page_number - 1]

            # Then extract tables from the matching pdfplumber page.
            try:
                tables = plumber_page.extract_tables() or []
            except Exception as error:
                tables = []
                warnings.append(
                    f"Page {page_number}: table extraction failed: {error}"
                )
            text_from_tables = [
                convert_table_to_text(table) for table in tables
            ]

            # OCR the full page when native text is absent/sparse or a scan
            # occupies most of the page; otherwise OCR embedded image regions.
            text_from_images = []
            native_text = "\n".join(page_text)
            full_page_ocr = len(re.sub(r"\W+", "", native_text)) < 80
            if _image_coverage(plumber_page) >= 0.55:
                full_page_ocr = True

            if full_page_ocr or plumber_page.images:
                try:
                    rendered_pages = convert_from_path(
                        str(pdf_file),
                        first_page=page_number,
                        last_page=page_number,
                        dpi=300,
                        poppler_path=poppler_path,
                    )
                    if rendered_pages:
                        page_image: Image.Image = rendered_pages[0].convert("RGB")
                        image_digest = hashlib.sha256(
                            f"{page_image.size}".encode("ascii")
                            + page_image.tobytes()
                        ).hexdigest()
                        previous_page = rendered_page_hashes.get(image_digest)
                        if previous_page is not None:
                            warnings.append(
                                f"Page {page_number}: rendered page image is "
                                f"identical to page {previous_page}; the source PDF "
                                "may repeat the same scanned page."
                            )
                        else:
                            rendered_page_hashes[image_digest] = page_number

                        if full_page_ocr:
                            targets = [(_correct_image_orientation(page_image), 3)]
                        else:
                            targets = []
                            for region in plumber_page.images:
                                image_crop = _crop_page_image(
                                    page_image, plumber_page, region
                                )
                                # Treat an embedded scan/chart/table as a text
                                # block. Enlarging small regions helps Tesseract.
                                page_mode = 6
                                if max(image_crop.size) < 2400:
                                    image_crop = image_crop.resize(
                                        (image_crop.width * 2, image_crop.height * 2)
                                    ).filter(ImageFilter.SHARPEN)
                                targets.append((
                                    _correct_image_orientation(image_crop),
                                    page_mode,
                                ))

                        known_text = "\n".join(
                            [native_text, *text_from_tables]
                        )
                        for target_image, page_mode in targets:
                            ocr_text, confidence = _read_ocr(
                                target_image, page_mode
                            )
                            if confidence < 55:
                                alternate_mode = 6 if page_mode != 6 else 11
                                alternate_text, alternate_confidence = (
                                    _read_ocr(target_image, alternate_mode)
                                )
                                if alternate_confidence > confidence:
                                    ocr_text = alternate_text
                                    confidence = alternate_confidence

                            ocr_text = _remove_duplicate_ocr_lines(ocr_text, known_text)
                            if ocr_text:
                                text_from_images.append(ocr_text)
                                known_text += "\n" + ocr_text
                            if confidence < 55:
                                warnings.append(
                                    f"Page {page_number}: OCR confidence is low "
                                    f"({confidence:.0f}/100); review the extracted text."
                                )
                except Exception as error:
                    warnings.append(
                        f"Page {page_number}: OCR failed: {error}"
                    )
            elif len(re.sub(r"\W+", "", native_text)) < 80:
                warnings.append(
                    f"Page {page_number}: little selectable text was found and "
                    "no embedded images were available for OCR."
                )

            page_content = page_text + text_from_tables
            for ocr_text in text_from_images:
                page_content.extend(
                    line for line in ocr_text.splitlines() if line.strip()
                )

            page_results[f"Page_{page_number}"] = {
                "page_text": page_text,
                "line_format": line_format,
                "text_from_images": text_from_images,
                "text_from_tables": text_from_tables,
                "page_content": page_content,
            }

    page_results["warnings"] = warnings
    return page_results
