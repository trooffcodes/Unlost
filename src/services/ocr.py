import os
import time
import io
import requests
from pathlib import Path
from dotenv import load_dotenv
from utils.logger import time_it

load_dotenv()

OCR_SPACE_KEY = os.getenv("OCR_SPACE_KEY")
LLAMA_CLOUD_API_KEY = os.getenv("LLAMA_CLOUD_API_KEY") or os.getenv("LlamaParse")
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff", ".gif"}

@time_it
def ocr_space(file_bytes: bytes, filename: str, language: str = "eng", timeout: int = 30) -> str:
    if not OCR_SPACE_KEY:
        raise ValueError("OCR_SPACE_KEY missing.")

    payload = {
        "apikey": OCR_SPACE_KEY,
        "language": language,
        "isOverlayRequired": False,
        "detectOrientation": True,
        "scale": True,
    }

    file_tuple = (filename, io.BytesIO(file_bytes), "image/jpeg")
    response = requests.post(
        "https://api.ocr.space/parse/image",
        files={"file": file_tuple},
        data=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    result = response.json()

    if result.get("IsErroredOnProcessing"):
        raise RuntimeError(f"OCR.space error: {result.get('ErrorMessage')}")

    parsed = result.get("ParsedResults")
    return parsed[0].get("ParsedText", "").strip() if parsed else ""

@time_it
def llamaparse(file_bytes: bytes, filename: str, poll_timeout: int = 120) -> str:
    if not LLAMA_CLOUD_API_KEY:
        raise ValueError("LLAMA_CLOUD_API_KEY missing.")

    base_url = "https://api.cloud.llamaindex.ai"
    headers = {"Authorization": f"Bearer {LLAMA_CLOUD_API_KEY}", "Accept": "application/json"}

    upload_resp = requests.post(
        f"{base_url}/api/v1/beta/files",
        headers=headers,
        files={"file": (filename, io.BytesIO(file_bytes), "application/pdf")},
        data={"purpose": "parse"},
        timeout=60,
    )
    upload_resp.raise_for_status()
    file_id = upload_resp.json()["id"]

    parse_resp = requests.post(
        f"{base_url}/api/v2/parse",
        headers={**headers, "Content-Type": "application/json"},
        json={"file_id": file_id, "tier": "fast", "version": "latest"},
        timeout=60,
    )
    parse_resp.raise_for_status()
    job_id = parse_resp.json()["id"]

    start_time = time.time()
    while time.time() - start_time < poll_timeout:
        status_resp = requests.get(
            f"{base_url}/api/v2/parse/{job_id}",
            headers=headers,
            params={"expand": "markdown"},
            timeout=60,
        )
        status_resp.raise_for_status()
        data = status_resp.json()
        status = data.get("job", {}).get("status")

        if status == "COMPLETED":
            if markdown := data.get("markdown_full"):
                return markdown
            pages = data.get("markdown", {}).get("pages", [])
            return "\n\n".join(p.get("markdown", "") for p in pages if p.get("markdown"))

        if status in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"LlamaParse job {status}: {data.get('job', {}).get('error_message')}")

        time.sleep(1.5)

    raise TimeoutError("LlamaParse timed out.")

@time_it
def extract_document_text(file_bytes: bytes, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return llamaparse(file_bytes, filename)
    if suffix in ALLOWED_IMAGE_EXTENSIONS:
        return ocr_space(file_bytes, filename)
    raise ValueError(f"Unsupported format: '{suffix}'")