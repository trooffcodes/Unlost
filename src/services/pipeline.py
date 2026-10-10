import io
import uuid
import zipfile
import threading
import json
from pathlib import Path
import time
from utils.storage import update_record
from werkzeug.utils import secure_filename

from config import Config, kv_db
from utils.logger import logger
from utils.validation import validate_upload
from utils.media import compress_for_ocr, compress_for_llm
from utils.telemetry import log_telemetry
from services.ocr import extract_document_text
from services.ai import extract_semantic_metadata, generate_embedding
from services.vector_store import add_to_store
from services.token_manager import user_token_manager

jobs_tracker = {}
jobs_lock = threading.Lock()

def _update_job_status(batch_id: str, filename: str, status: str):
    def change(job):
        job["files"][filename] = status
        if all(s.startswith(("DONE", "ERROR")) for s in job["files"].values()):
            job["status"] = "completed"
    if kv_db:
        update_record(f"job:{batch_id}", {}, change, ttl=86400)
    else:
        with jobs_lock:
            change(jobs_tracker[batch_id])


def _read_native_text(file_bytes: bytes) -> str:
    for encoding in ("utf-8", "latin-1", "cp1252"):
        try:
            return file_bytes.decode(encoding)[:15000]
        except UnicodeDecodeError:
            continue
    return ""

def process_single_file(batch_id: str, device_id: str, filename: str, file_bytes: bytes):
    try:
        if not user_token_manager.consume(device_id, max(50, min(len(file_bytes), 15000) // 4 + 500)):
            _update_job_status(batch_id, filename, "ERROR: Token Limit Exceeded")
            return

        _update_job_status(batch_id, filename, "Processing...")
        
        ext = Path(filename).suffix.lower()

        extracted_text = ""
        llm_bytes = file_bytes

        if ext in Config.ALLOWED_TEXT_EXT:
            extracted_text = _read_native_text(file_bytes)
        elif ext in Config.ALLOWED_IMAGE_EXT or ext in Config.ALLOWED_PDF_EXT:
            try:
                ocr_bytes = compress_for_ocr(file_bytes, ext)
                extracted_text = extract_document_text(ocr_bytes, filename)
            except Exception as ocr_err:
                logger.warning(f"OCR step bypassed for {filename}: {ocr_err}")
                extracted_text = ""
            llm_bytes = compress_for_llm(file_bytes, ext)

        metadata = extract_semantic_metadata(llm_bytes, filename, extracted_text)

        folder_clean = secure_filename(metadata.get("suggested_folder", "General")) or "General"
        # Vercel scratch files are not durable storage. Keep only searchable metadata.
        rel_path = f"{folder_clean}/{filename}"

        semantic_text = metadata.get("semantic_search_text") or f"{filename} {extracted_text[:400]}"
        embedding = generate_embedding(semantic_text)
        add_to_store(device_id, filename, rel_path, metadata, embedding)


        from utils.webhook import notify_file
        notify_file(device_id, filename, file_bytes)
        _update_job_status(batch_id, filename, "DONE")
        log_telemetry("upload_success", device_id, {"filename": filename, "folder": folder_clean})

    except Exception as e:
        logger.error("Pipeline processing failure (%s)", type(e).__name__)
        _update_job_status(batch_id, filename, "ERROR: Processing failed; please retry")
        log_telemetry("upload_error", device_id, {"filename": filename, "error": type(e).__name__})

def queue_processing_batch(user_id: str, files_data: list[tuple[str, bytes]]) -> str:
    batch_id = str(uuid.uuid4())
    flat_files = []

    expanded_bytes = 0

    def append_file(filename, data):
        nonlocal expanded_bytes
        safe = secure_filename(filename)
        if not safe:
            raise ValueError("Invalid filename")
        error = validate_upload(data, safe, None)
        if error:
            raise ValueError(error)
        expanded_bytes += len(data)
        if len(flat_files) >= Config.MAX_FILES_PER_BATCH or expanded_bytes > Config.MAX_EXPANDED_BYTES:
            raise ValueError(f"Upload exceeds {Config.MAX_FILES_PER_BATCH} files or the expanded size limit")
        flat_files.append((safe, data))

    for filename, file_bytes in files_data:
        error = validate_upload(file_bytes, filename, None)
        if error:
            raise ValueError(error)
        if Path(filename).suffix.lower() == ".zip":
            try:
                with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
                    if len(archive.infolist()) > 1000:
                        raise ValueError("Archive contains too many entries")
                    for info in archive.infolist():
                        if info.is_dir():
                            continue
                        if info.flag_bits & 1:
                            raise ValueError("Encrypted archives are not supported")
                        if Path(info.filename).suffix.lower() not in Config.ALLOWED_EXTENSIONS - {".zip"}:
                            raise ValueError("Archive contains an unsupported file type")
                        if info.file_size > Config.MAX_FILE_SIZE or info.file_size + expanded_bytes > Config.MAX_EXPANDED_BYTES:
                            raise ValueError("Archive exceeds the expanded size limit")
                        if len(flat_files) >= Config.MAX_FILES_PER_BATCH:
                            raise ValueError(f"Archive exceeds {Config.MAX_FILES_PER_BATCH} files")
                        append_file(Path(info.filename).name, archive.read(info))
            except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
                raise ValueError("Archive cannot be read") from exc
        else:
            append_file(filename, file_bytes)

    if not flat_files:
        raise ValueError("No supported files received")

    unique_files = {}
    for fname, fbytes in flat_files:
        name_root, ext_part = Path(fname).stem, Path(fname).suffix
        counter = 1
        resolved_name = fname
        while resolved_name in unique_files and unique_files[resolved_name] != fbytes:
            resolved_name = f"{name_root}_{counter}{ext_part}"
            counter += 1
        unique_files[resolved_name] = fbytes

    final_queue = list(unique_files.items())
    job_state = {
        "user_id": user_id,
        "created_at": time.time(),
        "status": "processing",
        "files": {fname: "Queued" for fname, _ in final_queue}
    }

    if kv_db:
        kv_db.set(f"job:{batch_id}", json.dumps(job_state), ex=86400)
    else:
        with jobs_lock:
            cutoff = time.time() - 86400
            for key in list(jobs_tracker):
                if jobs_tracker[key].get("created_at", 0) < cutoff:
                    del jobs_tracker[key]
            jobs_tracker[batch_id] = job_state

    # Complete work before returning: serverless instances can freeze after a response.
    for filename, data in final_queue:
        process_single_file(batch_id, user_id, filename, data)
    return batch_id


def get_job_status(batch_id: str, user_id: str) -> dict:
    if kv_db:
        raw = kv_db.get(f"job:{batch_id}")
        job = json.loads(raw) if raw else {}
    else:
        with jobs_lock:
            job = dict(jobs_tracker.get(batch_id, {}))
    if job.get("user_id") != user_id:
        return {"status": "not_found", "files": {}}
    return {"status": job["status"], "files": job["files"]}
