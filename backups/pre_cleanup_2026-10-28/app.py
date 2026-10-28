
import io
import json
import zipfile
import tempfile
from pathlib import Path

import streamlit as st

from document_extractor import (
    extract_text,
    extract_document_images,
    SUPPORTED_FORMATS,
    IMAGE_FORMATS,
)
from pdf_combined_extraction import extract_combined_pdf

st.set_page_config(
    page_title="Document Text Extractor",
    page_icon="📄",
    layout="wide"
)

st.title("📄 Document Text Extractor")
st.write("Extract text from PDF, DOCX, XLSX, CSV, and images.")

st.info(
    "Image OCR supports English text. "
    "PDFs include text, table, font/layout extraction, and scanned-page OCR."
)

supported_formats = sorted(set(SUPPORTED_FORMATS + IMAGE_FORMATS))

uploaded_file = st.file_uploader(
    "Upload a document or image",
    type=[extension.lstrip(".") for extension in supported_formats]
)

if uploaded_file is not None:
    extension = Path(uploaded_file.name).suffix.lower()

    with tempfile.NamedTemporaryFile(
        delete=False, suffix=extension
    ) as temp_file:
        temp_file.write(uploaded_file.getvalue())
        temp_path = Path(temp_file.name)

    try:
        with st.spinner("Extracting text..."):
            pdf_data = None
            if extension == ".pdf":
                pdf_data = extract_combined_pdf(temp_path)
                extracted_text = "\n\n".join(
                    f"--- {page_name.replace('_', ' ')} ---\n"
                    + "\n".join(page_data["page_content"])
                    for page_name, page_data in pdf_data.items()
                )
            else:
                extracted_text = extract_text(temp_path)

        st.success("Text extraction completed!")
        st.subheader("Extracted Text")

        if extracted_text:
            st.text_area(
                "Text result",
                value=extracted_text,
                height=350
            )

            st.download_button(
                "Download TXT",
                data=extracted_text.encode("utf-8"),
                file_name=f"{Path(uploaded_file.name).stem}_extracted.txt",
                mime="text/plain"
            )

            if pdf_data is not None:
                st.download_button(
                    "Download structured JSON",
                    data=json.dumps(pdf_data, ensure_ascii=False, indent=2),
                    file_name=f"{Path(uploaded_file.name).stem}_extracted.json",
                    mime="application/json"
                )
        else:
            st.warning("No text was found in this file.")

        if pdf_data is not None:
            st.subheader("PDF results by page")
            for page_name, page_data in pdf_data.items():
                with st.expander(page_name.replace("_", " "), expanded=True):
                    st.markdown("**page_text — selectable text blocks**")
                    st.text_area(
                        f"{page_name} page_text",
                        value="\n".join(page_data["page_text"]),
                        height=150,
                        key=f"{page_name}_page_text",
                    )

                    formatted_lines = []
                    for block_number, formats in enumerate(
                        page_data["line_format"], start=1
                    ):
                        format_text = ", ".join(
                            f"{font}, {size} pt" for font, size in formats
                        ) or "Formatting not available"
                        formatted_lines.append(
                            f"Text block {block_number}: {format_text}"
                        )
                    st.markdown("**line_format — font family and size per text block**")
                    st.text_area(
                        f"{page_name} line_format",
                        value="\n".join(formatted_lines),
                        height=120,
                        key=f"{page_name}_line_format",
                    )

                    st.markdown("**text_from_images — OCR text**")
                    st.text_area(
                        f"{page_name} text_from_images",
                        value="\n\n".join(page_data["text_from_images"]),
                        height=150,
                        key=f"{page_name}_text_from_images",
                    )

                    st.markdown("**text_from_tables — extracted tables**")
                    st.text_area(
                        f"{page_name} text_from_tables",
                        value="\n\n".join(page_data["text_from_tables"]),
                        height=150,
                        key=f"{page_name}_text_from_tables",
                    )

                    st.markdown("**page_content — combined page text**")
                    st.text_area(
                        f"{page_name} page_content",
                        value="\n".join(page_data["page_content"]),
                        height=200,
                        key=f"{page_name}_page_content",
                    )

        if extension in [".pdf", ".docx", ".xlsx"]:
            with st.expander("View images and PDF page previews"):
                images = extract_document_images(temp_path)

                if images:
                    zip_buffer = io.BytesIO()

                    with zipfile.ZipFile(
                        zip_buffer, "w", zipfile.ZIP_DEFLATED
                    ) as archive:
                        for image in images:
                            filename = (
                                f"{image['name']}.{image['extension']}"
                            )
                            archive.writestr(filename, image["data"])

                    st.download_button(
                        "Download Images ZIP",
                        data=zip_buffer.getvalue(),
                        file_name="extracted_images.zip",
                        mime="application/zip"
                    )

                    for image in images:
                        if image["extension"].lower() in [
                            "png", "jpg", "jpeg", "bmp", "tif", "tiff"
                        ]:
                            st.image(
                                image["data"],
                                caption=image["name"],
                                use_container_width=True
                            )
                else:
                    st.info("No embedded images found.")

    except Exception as error:
        st.error(f"Extraction failed: {error}")

    finally:
        temp_path.unlink(missing_ok=True)
