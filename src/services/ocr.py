import os
import io
import time
import requests
import mimetypes
from pathlib import Path
from utils.logger import time_it, logger

OCR_SPACE_KEY = os.getenv("OCR_SPACE_KEY")
LLAMA_CLOUD_API_KEY = os.getenv("LLAMA_CLOUD_API_KEY") or os.getenv("LlamaParse")

def ocr_space(file_bytes: bytes, filename: str, timeout: int = 25) -> str:
    if not OCR_SPACE_KEY:
        raise ValueError("OCR_SPACE_KEY not configured.")

    mime_type, _ = mimetypes.guess_type(filename)
    payload = {
        "apikey": OCR_SPACE_KEY,
        "language": "eng",
        "isOverlayRequired": "false",
        "detectOrientation": "true",
        "scale": "true",
    }
    files = {"file": (filename, io.BytesIO(file_bytes), mime_type or "image/jpeg")}

    res = requests.post("https://api.ocr.space/parse/image", files=files, data=payload, timeout=timeout)
    res.raise_for_status()
    result = res.json()

    if result.get("IsErroredOnProcessing"):
        raise RuntimeError(f"OCR.Space Error: {result.get('ErrorMessage')}")

    parsed = result.get("ParsedResults", [])
    return parsed[0].get("ParsedText", "").strip() if parsed else ""

@time_it
def llamaparse(file_bytes: bytes, filename: str, timeout: int = 40) -> str:
    if not LLAMA_CLOUD_API_KEY:
        raise ValueError("LLAMA_CLOUD_API_KEY not configured.")

    base_url = "https://api.cloud.llamaindex.ai"
    headers = {"Authorization": f"Bearer {LLAMA_CLOUD_API_KEY}", "Accept": "application/json"}

    upload = requests.post(
        f"{base_url}/api/v1/beta/files",
        headers=headers,
        files={"file": (filename, io.BytesIO(file_bytes), "application/pdf")},
        data={"purpose": "parse"},
        timeout=30,
    )
    upload.raise_for_status()
    file_id = upload.json()["id"]

    parse_job = requests.post(
        f"{base_url}/api/v2/parse",
        headers={**headers, "Content-Type": "application/json"},
        json={"file_id": file_id, "tier": "fast", "version": "latest"},
        timeout=30,
    )
    parse_job.raise_for_status()
    job_id = parse_job.json()["id"]

    start = time.time()
    while time.time() - start < timeout:
        status_res = requests.get(f"{base_url}/api/v2/parse/{job_id}", headers=headers, timeout=20)
        status_res.raise_for_status()
        data = status_res.json()
        status = data.get("job", {}).get("status")

        if status == "COMPLETED":
            if full := data.get("markdown_full"):
                return full
            pages = data.get("markdown", {}).get("pages", [])
            return "\n\n".join(p.get("markdown", "") for p in pages if p.get("markdown"))
        if status in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"LlamaParse error: {data.get('job', {}).get('error_message')}")
        time.sleep(1.5)

    raise TimeoutError("LlamaParse processing timed out.")

@time_it
def extract_document_text(file_bytes: bytes, filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return llamaparse(file_bytes, filename)
    if ext in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
        return ocr_space(file_bytes, filename)
    return ""
