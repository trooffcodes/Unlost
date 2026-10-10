import io
import time
import mimetypes
from pathlib import Path

import requests
import fitz  

from config import Config
from utils.logger import time_it, logger


LLAMA_BASE_URL = "https://api.cloud.llamaindex.ai"
OCR_SPACE_URL = "https://api.ocr.space/parse/image"

UPLOAD_TIMEOUT = 30
LLAMAPARSE_TIMEOUT = 60
OCR_TIMEOUT = 30
POLL_INTERVAL = 1.5
MAX_OCR_PAGES = 10


def _response_json(response, service_name):
    """Parse and validate a JSON API response."""
    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"{service_name} returned invalid JSON "
            f"(HTTP {response.status_code})."
        ) from exc

    if not isinstance(data, dict):
        raise RuntimeError(
            f"{service_name} returned an unexpected response type: "
            f"{type(data).__name__}"
        )

    return data


def _error_message(data):
    """Extract an error message safely."""
    if not isinstance(data, dict):
        return str(data)

    for key in ("detail", "message", "error"):
        value = data.get(key)

        if isinstance(value, str) and value.strip():
            return value

        if isinstance(value, dict):
            message = (
                value.get("message")
                or value.get("detail")
                or value.get("type")
            )
            if message:
                return str(message)

    job = data.get("job")
    if isinstance(job, dict):
        message = job.get("error_message")
        if message:
            return str(message)

    return "No error details provided"


def _ocr_space_image(
    image_bytes: bytes,
    filename: str,
    timeout: int = OCR_TIMEOUT,
) -> str:
    """OCR one image using OCR.Space."""
    api_key = Config.OCR_SPACE_KEY

    if not api_key:
        raise ValueError("OCR_SPACE_KEY is not configured in Config.")

    mime_type, _ = mimetypes.guess_type(filename)

    payload = {
        "apikey": api_key,
        "language": "eng",
        "isOverlayRequired": "false",
        "detectOrientation": "true",
        "scale": "true",
    }

    files = {
        "file": (
            filename,
            io.BytesIO(image_bytes),
            mime_type or "image/jpeg",
        )
    }

    response = requests.post(
        OCR_SPACE_URL,
        files=files,
        data=payload,
        timeout=timeout,
    )
    response.raise_for_status()

    result = _response_json(response, "OCR.Space")

    if result.get("IsErroredOnProcessing"):
        raise RuntimeError(
            f"OCR.Space error: {_error_message(result)}"
        )

    parsed_results = result.get("ParsedResults") or []

    if not isinstance(parsed_results, list):
        raise RuntimeError(
            "OCR.Space returned an invalid ParsedResults field."
        )

    text_parts = []

    for item in parsed_results:
        if not isinstance(item, dict):
            continue

        text = item.get("ParsedText")

        if isinstance(text, str) and text.strip():
            text_parts.append(text.strip())

    return "\n\n".join(text_parts)


@time_it
def ocr_space(
    file_bytes: bytes,
    filename: str,
    timeout: int = OCR_TIMEOUT,
) -> str:
    """Public OCR.Space wrapper for image files."""
    try:
        return _ocr_space_image(file_bytes, filename, timeout)
    except Exception:
        logger.exception("OCR.Space failed for %s", filename)
        raise


def _extract_pdf_text_locally(file_bytes: bytes) -> str:
    """Extract embedded text from a PDF using PyMuPDF."""
    parts = []

    with fitz.open(stream=file_bytes, filetype="pdf") as document:
        for page in document:
            text = page.get_text("text")

            if text and text.strip():
                parts.append(text.strip())

    return "\n\n".join(parts)


def _ocr_pdf_pages(
    file_bytes: bytes,
    max_pages: int = MAX_OCR_PAGES,
) -> str:
    """Render PDF pages and OCR them using OCR.Space."""
    if not Config.OCR_SPACE_KEY:
        logger.warning(
            "OCR.Space key is missing; scanned PDF OCR is unavailable."
        )
        return ""

    parts = []

    with fitz.open(stream=file_bytes, filetype="pdf") as document:
        page_count = min(len(document), max_pages)

        for index in range(page_count):
            page = document.load_page(index)

            pixmap = page.get_pixmap(
                matrix=fitz.Matrix(1.5, 1.5),
                alpha=False,
            )

            image_bytes = pixmap.tobytes("png")

            try:
                text = _ocr_space_image(
                    image_bytes,
                    f"page_{index + 1}.png",
                )

                if text.strip():
                    parts.append(
                        f"Page {index + 1}\n{text.strip()}"
                    )

            except Exception:
                logger.exception(
                    "OCR failed on PDF page %d",
                    index + 1,
                )

    return "\n\n".join(parts)


@time_it
def llamaparse(
    file_bytes: bytes,
    filename: str,
    timeout: int = LLAMAPARSE_TIMEOUT,
) -> str:
    """Upload a PDF to LlamaParse and retrieve its Markdown."""
    api_key = Config.LLAMA_CLOUD_API_KEY

    if not api_key:
        raise ValueError("LLAMA_CLOUD_API_KEY is not configured in Config.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }

    # 1. Upload the PDF.
    upload_response = requests.post(
        f"{LLAMA_BASE_URL}/api/v1/beta/files",
        headers=headers,
        files={"file": (filename, io.BytesIO(file_bytes), "application/pdf")},
        data={"purpose": "parse"},
        timeout=UPLOAD_TIMEOUT,
    )
    upload_response.raise_for_status()

    upload_data = _response_json(upload_response, "LlamaParse upload")
    file_id = upload_data.get("id")

    if not file_id:
        raise RuntimeError("LlamaParse upload response has no file ID.")

    # 2. Create the parsing job.
    job_response = requests.post(
        f"{LLAMA_BASE_URL}/api/v2/parse",
        headers={**headers, "Content-Type": "application/json"},
        json={"file_id": file_id, "tier": "fast", "version": "latest"},
        timeout=UPLOAD_TIMEOUT,
    )
    job_response.raise_for_status()

    job_data = _response_json(job_response, "LlamaParse job creation")
    job_id = job_data.get("id")

    if not job_id:
        raise RuntimeError("LlamaParse job creation response has no job ID.")

    # 3. Poll until the job completes or times out.
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        response = requests.get(
            f"{LLAMA_BASE_URL}/api/v2/parse/{job_id}",
            headers=headers,
            timeout=20,
        )
        response.raise_for_status()
        data = _response_json(response, "LlamaParse status")
        job = data.get("job") or {}

        if not isinstance(job, dict):
            raise RuntimeError("LlamaParse returned an invalid job object.")

        status = job.get("status")

        if status == "COMPLETED":
            # FIX: Check for direct string representations first to prevent crashes
            for key in ("markdown_full", "markdown", "text_full", "text"):
                val = data.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()

            markdown = data.get("markdown") or {}

            if isinstance(markdown, dict):
                pages = markdown.get("pages") or []
            elif isinstance(markdown, list):
                pages = markdown
            else:
                pages = []

            # FIX: Fallback to checking "text" key for pages if markdown is missing them
            if not pages:
                text_dict = data.get("text") or {}
                if isinstance(text_dict, dict):
                    pages = text_dict.get("pages") or []
                elif isinstance(text_dict, list):
                    pages = text_dict

            if not isinstance(pages, list):
                pages = []

            parts = []
            for page in pages:
                if not isinstance(page, dict):
                    continue

                # Check both properties to ensure we don't skip over text data
                page_text = page.get("markdown") or page.get("text")

                if isinstance(page_text, str) and page_text.strip():
                    parts.append(page_text.strip())

            if parts:
                return "\n\n".join(parts)

            raise RuntimeError(
                "LlamaParse completed without returning text. "
                f"Response keys: {list(data.keys())}"
            )

        if status in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"LlamaParse {status}: {_error_message(data)}")

        if not status:
            logger.warning("LlamaParse returned no job status; response keys: %s", list(data.keys()))

        time.sleep(POLL_INTERVAL)

    raise TimeoutError(f"LlamaParse timed out after {timeout}s for {filename}.")


@time_it
def extract_document_text(
    file_bytes: bytes,
    filename: str,
) -> str:
    """
    Extract text from supported PDFs and images.

    PDF fallback order:
      1. LlamaParse
      2. Local PDF text extraction
      3. OCR.Space on rendered pages
    """
    if not file_bytes:
        raise ValueError(f"Empty file: {filename}")

    extension = Path(filename).suffix.lower()

    if extension in Config.ALLOWED_PDF_EXT:
        # Primary PDF parser.
        try:
            text = llamaparse(file_bytes, filename)

            if text and text.strip():
                return text.strip()

            logger.warning(
                "LlamaParse returned empty text for %s",
                filename,
            )

        except Exception:
            logger.exception(
                "LlamaParse failed for %s; trying local extraction.",
                filename,
            )

        # Fallback: extract any embedded PDF text.
        try:
            text = _extract_pdf_text_locally(file_bytes)

            if text and text.strip():
                logger.info(
                    "Local PDF extraction succeeded for %s",
                    filename,
                )
                return text.strip()

        except Exception:
            logger.exception(
                "Local PDF extraction failed for %s",
                filename,
            )

        # Fallback: OCR scanned PDF pages.
        try:
            text = _ocr_pdf_pages(file_bytes)

            if text and text.strip():
                logger.info(
                    "PDF OCR fallback succeeded for %s",
                    filename,
                )
                return text.strip()

        except Exception:
            logger.exception(
                "PDF OCR fallback failed for %s",
                filename,
            )

        logger.error(
            "All PDF extraction methods failed for %s",
            filename,
        )
        return ""

    if extension in Config.ALLOWED_IMAGE_EXT:
        return ocr_space(file_bytes, filename)

    if extension in Config.ALLOWED_TEXT_EXT:
        try:
            return file_bytes.decode("utf-8-sig").strip()
        except UnicodeDecodeError:
            logger.exception(
                "Could not decode text document %s",
                filename,
            )
            return ""

    logger.warning(
        "Unsupported document type: %s",
        filename,
    )
    return ""