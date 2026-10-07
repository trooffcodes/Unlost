import requests
from dotenv import load_dotenv
import os
from time import perf_counter

load_dotenv()
API_KEY = os.getenv("OCR_KEY")

def ocr_space_file(filename, language='eng'):
    payload = {
        'apikey': API_KEY,
        'language': language,
        'isOverlayRequired': False
    }
    with open(filename, 'rb') as f:
        r = requests.post(
            'https://api.ocr.space/parse/image',
            files={filename: f},
            data=payload
        )
    result = r.json()
    return result['ParsedResults'][0]['ParsedText']

def parse_with_llamaparse(file_path: str) -> str:
    """
    Parse a document using LlamaParse and return Markdown.

    Prints the time taken for:
    - File upload
    - Parse job creation
    - Document processing
    - Total execution
    """

    total_start = time.perf_counter()

    api_key = os.environ["LlamaParse"]
    base_url = "https://api.cloud.llamaindex.ai"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }

    start = time.perf_counter()

    with open(file_path, "rb") as f:
        response = requests.post(
            f"{base_url}/api/v1/beta/files",
            headers=headers,
            files={
                "file": (
                    os.path.basename(file_path),
                    f,
                    "application/pdf",
                )
            },
            data={
                "purpose": "parse",
            },
            timeout=60,
        )

    response.raise_for_status()

    file_id = response.json()["id"]

    upload_time = time.perf_counter() - start

    print(f"Uploaded: {file_id}")
    print(f"Upload time: {upload_time:.2f}s")

    start = time.perf_counter()

    response = requests.post(
        f"{base_url}/api/v2/parse",
        headers={
            **headers,
            "Content-Type": "application/json",
        },
        json={
            "file_id": file_id,
            "tier": "fast",
            "version": "latest",
        },
        timeout=60,
    )

    if not response.ok:
        raise RuntimeError(
            f"Parse request failed ({response.status_code}):\n"
            f"{response.text}"
        )

    job_id = response.json()["id"]

    job_creation_time = time.perf_counter() - start

    print(f"Parse job: {job_id}")
    print(f"Job creation time: {job_creation_time:.2f}s")

    start = time.perf_counter()

    while True:

        response = requests.get(
            f"{base_url}/api/v2/parse/{job_id}",
            headers=headers,
            params={
                "expand": "markdown",
            },
            timeout=60,
        )

        response.raise_for_status()

        result = response.json()
        status = result["job"]["status"]

        print(f"Status: {status}")

        if status == "COMPLETED":
            break

        if status in ("FAILED", "CANCELLED"):
            raise RuntimeError(
                result["job"].get(
                    "error_message",
                    "LlamaParse failed",
                )
            )

        time.sleep(1)

    processing_time = time.perf_counter() - start

    print(f"Processing time: {processing_time:.2f}s")

    markdown = result.get("markdown_full")

    if markdown:
        total_time = time.perf_counter() - total_start

        print(f"Total time: {total_time:.2f}s")

        return markdown

    pages = (
        result
        .get("markdown", {})
        .get("pages", [])
    )

    if pages:
        markdown = "\n\n".join(
            page.get("markdown", "")
            for page in pages
        )

        total_time = time.perf_counter() - total_start

        print(f"Total time: {total_time:.2f}s")

        return markdown

    raise RuntimeError(
        "Parsing completed, but no Markdown was found."
    )