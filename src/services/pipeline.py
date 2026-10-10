import io
import uuid
import zipfile
import threading
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
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

executor = ThreadPoolExecutor(max_workers=4)
jobs_tracker = {}
jobs_lock = threading.Lock()

def _update_job_status(batch_id: str, filename: str, status: str):
    if kv_db:
        try:
            val = kv_db.get(f"job:{batch_id}")
            if val:
                job = json.loads(val)
                job["files"][filename] = status
                statuses = list(job["files"].values())
                if all(s.startswith("DONE") or s.startswith("ERROR") for s in statuses):
                    job["status"] = "completed"
                kv_db.set(f"job:{batch_id}", json.dumps(job), ex=86400)
            return
        except Exception as e:
            logger.error(f"Job update KV Error: {e}")

    with jobs_lock:
        if batch_id not in jobs_tracker:
            return
        jobs_tracker[batch_id]["files"][filename] = status
        statuses = list(jobs_tracker[batch_id]["files"].values())
        if all(s.startswith("DONE") or s.startswith("ERROR") for s in statuses):
            jobs_tracker[batch_id]["status"] = "completed"

def _read_native_text(file_bytes: bytes) -> str:
    for encoding in ("utf-8", "latin-1", "cp1252"):
        try:
            return file_bytes.decode(encoding)[:15000]
        except UnicodeDecodeError:
            continue
    return ""

def process_single_file(batch_id: str, device_id: str, filename: str, file_bytes: bytes):
    try:
        if user_token_manager.is_over_limit(device_id):
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
        target_dir = Config.USER_DATA_DIR / device_id / folder_clean

        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            target_file = target_dir / filename
            with open(target_file, "wb") as f:
                f.write(file_bytes)
            rel_path = str(target_file.relative_to(Config.USER_DATA_DIR))
        except Exception:
            rel_path = f"{folder_clean}/{filename}"

        semantic_text = metadata.get("semantic_search_text") or f"{filename} {extracted_text[:400]}"
        embedding = generate_embedding(semantic_text)
        add_to_store(device_id, filename, rel_path, metadata, embedding)

        estimated_tokens = max(50, (len(semantic_text) + len(extracted_text)) // 4)
        user_token_manager.track_usage(device_id, estimated_tokens)

        _update_job_status(batch_id, filename, "DONE")
        log_telemetry("upload_success", device_id, {"filename": filename, "folder": folder_clean})

    except Exception as e:
        logger.error(f"[{filename}] Pipeline processing failure: {e}", exc_info=True)
        _update_job_status(batch_id, filename, f"ERROR: {str(e)}")
        log_telemetry("upload_error", device_id, {"filename": filename, "error": str(e)})

def queue_processing_batch(user_id: str, files_data: list[tuple[str, bytes]]) -> str:
    batch_id = str(uuid.uuid4())
    flat_files = []

    for filename, file_bytes in files_data:
        ext = Path(filename).suffix.lower()
        if ext == ".zip":
            try:
                with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
                    for info in z.infolist():
                        if info.is_dir():
                            continue
                        inner_ext = Path(info.filename).suffix.lower()
                        if inner_ext in Config.ALLOWED_EXTENSIONS and inner_ext != ".zip":
                            if info.file_size <= Config.MAX_FILE_SIZE and len(flat_files) < Config.MAX_FILES_PER_BATCH:
                                flat_files.append((Path(info.filename).name, z.read(info.filename)))
            except Exception as e:
                logger.error(f"Error unpacking ZIP: {e}")
        elif ext in Config.ALLOWED_EXTENSIONS:
            if len(flat_files) < Config.MAX_FILES_PER_BATCH:
                flat_files.append((filename, file_bytes))

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
        "status": "processing" if final_queue else "completed",
        "files": {fname: "Queued" for fname, _ in final_queue}
    }

    if kv_db:
        kv_db.set(f"job:{batch_id}", json.dumps(job_state), ex=86400)
    else:
        with jobs_lock:
            jobs_tracker[batch_id] = job_state

    user_folder = Config.USER_DATA_DIR / user_id
    try:
        user_folder.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    valid_queue = []
    for fname, fbytes in final_queue:
        validation_error = validate_upload(fbytes, fname, user_folder)
        if validation_error:
            _update_job_status(batch_id, fname, f"ERROR: {validation_error}")
        else:
            valid_queue.append((fname, fbytes))

    # CRITICAL SERVERLESS FIX: Await futures to prevent AWS Lambda freeze
    if Config.IS_VERCEL:
        futures = [executor.submit(process_single_file, batch_id, user_id, f, b) for f, b in valid_queue]
        for future in futures:
            try:
                future.result()
            except Exception as e:
                logger.error(f"Vercel Execution Fault: {e}")
    else:
        for fname, fbytes in valid_queue:
            executor.submit(process_single_file, batch_id, user_id, fname, fbytes)

    return batch_id

def get_job_status(batch_id: str) -> dict:
    if kv_db:
        try:
            val = kv_db.get(f"job:{batch_id}")
            if val:
                return json.loads(val)
        except Exception:
            pass
        return {"status": "not_found", "files": {}}

    with jobs_lock:
        return jobs_tracker.get(batch_id, {"status": "not_found", "files": {}})
