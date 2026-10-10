import hmac
import re
import io
from PIL import Image
from werkzeug.exceptions import BadRequest
import shutil
import uuid
import base64
from pathlib import Path
from flask import Blueprint, jsonify, request, render_template, Response, send_from_directory, session
from functools import wraps
from werkzeug.utils import secure_filename

from config import Config, kv_db
from utils.logger import logger
from utils.operations import device_operation
from utils.telemetry import log_telemetry, log_feedback, get_request_metadata
from services.ai import generate_embedding
from services.vector_store import search_store, clear_user_data, get_user_files
from services.pipeline import queue_processing_batch, get_job_status
from services.token_manager import user_token_manager

api_bp = Blueprint("api", __name__)

def get_device_id(req) -> str:
    # The signed session is the credential; untrusted legacy IDs are never accepted.
    if not re.fullmatch(r"[a-f0-9]{32}", str(session.get("device_id", ""))):
        session["device_id"] = uuid.uuid4().hex
        session.permanent = True
    return session["device_id"]


def json_object():
    data = request.get_json()
    if not isinstance(data, dict):
        raise BadRequest("Expected a JSON object")
    return data


def make_safe_filename(original_name: str) -> str:
    safe = secure_filename(original_name)
    if not safe or safe.startswith("."):
        safe = f"doc_{uuid.uuid4().hex[:8]}{Path(original_name).suffix}"
    return safe

@api_bp.route("/")
def index():
    get_device_id(request)
    return render_template("index.html", upload_config={"MAX_FILE_SIZE": Config.MAX_FILE_SIZE, "MAX_BATCH_SIZE": 50, "MAX_REQUEST_FILES": Config.MAX_FILES_PER_BATCH, "MAX_REQUEST_SIZE": Config.MAX_CONTENT_LENGTH})

@api_bp.route("/files", methods=["GET"])
def get_files():
    device_id = get_device_id(request)
    try:
        files = get_user_files(device_id)
        return jsonify({"success": True, "files": files})
    except Exception as e:
        logger.error(f"Failed to fetch library for device {device_id}: {e}")
        return jsonify({"success": False, "error": "Could not retrieve library files"}), 500

@api_bp.route("/usage", methods=["GET"])
def get_usage():
    device_id = get_device_id(request)
    
    meta = get_request_metadata(request)
    user_token_manager.register_user(device_id, meta)
    
    return jsonify({"success": True, "data": user_token_manager.get_usage_stats(device_id)})

@api_bp.route("/clear_data", methods=["POST"])
def perform_clear_data():
    device_id = get_device_id(request)
    log_telemetry("clear_data", device_id)

    with device_operation(device_id):
        clear_user_data(device_id)
    user_dir = Config.USER_DATA_DIR / device_id
    if user_dir.exists():
        try:
            shutil.rmtree(user_dir)
        except Exception as e:
            logger.error(f"Error purging local files: {e}")

    return jsonify({"success": True, "message": "Storage successfully cleared. Token limit preserved."})

@api_bp.route("/upload", methods=["POST"])
def upload():
    device_id = get_device_id(request)

    if user_token_manager.is_over_limit(device_id):
        return jsonify({"success": False, "error": "Token limit reached. Limit resets every 48 hours."}), 403

    files = request.files.getlist("files")
    if not files or not files[0].filename:
        return jsonify({"success": False, "error": "No files received"}), 400

    if len(files) > Config.MAX_FILES_PER_BATCH:
        return jsonify({"success": False, "error": f"Max {Config.MAX_FILES_PER_BATCH} files allowed per batch"}), 400

    files_data = []
    for file in files:
        data = file.read(Config.MAX_FILE_SIZE + 1)
        if len(data) > Config.MAX_FILE_SIZE:
            return jsonify(success=False, error="File exceeds the upload size limit"), 413
        files_data.append((make_safe_filename(file.filename), data))

    try:
        with device_operation(device_id):
            batch_id = queue_processing_batch(device_id, files_data)
        return jsonify({"success": True, "batch_id": batch_id})
    except ValueError as exc:
        return jsonify(success=False, error=str(exc)), 400

@api_bp.route("/status/<batch_id>", methods=["GET"])
def check_status(batch_id):
    status_data = get_job_status(batch_id, get_device_id(request))
    if status_data.get("status") == "not_found":
        return jsonify({"success": False, "error": "Job batch not found"}), 404
    return jsonify({"success": True, "data": status_data})

@api_bp.route("/search", methods=["POST"])
def search_documents():
    device_id = get_device_id(request)
    query = json_object().get("query", "")
    if not isinstance(query, str) or len(query) > 2000:
        raise BadRequest("Query must be a string of at most 2000 characters")
    query = query.strip()
    if user_token_manager.is_over_limit(device_id):
        return jsonify(success=False, error="Token limit reached; resets every 48 hours"), 403
    if not query:
        return jsonify({"success": False, "error": "Search query required"}), 400

    if not user_token_manager.consume(device_id, max(1, len(query) // 4)):
        return jsonify(success=False, error="Token limit reached; resets every 48 hours"), 403
    try:
        log_telemetry("search", device_id, {"query": query})
        query_embedding = generate_embedding(query)

        results = search_store(device_id, query_embedding)
        return jsonify({"success": True, "results": results})
    except Exception as exc:
        logger.error(f"Search API error: {exc}")
        return jsonify({"success": False, "error": "Search query failed"}), 500

@api_bp.route("/feedback", methods=["POST"])
def submit_feedback():
    device_id = get_device_id(request)
    message = request.form.get("message", "").strip()
    if len(message) > 4000:
        raise BadRequest("Feedback must be at most 4000 characters")
    image_file = request.files.get("image")
    
    client_data = {
        "resolution": request.form.get("resolution"),
        "time_on_page": request.form.get("time_on_page"),
        "current_url": request.form.get("current_url")
    }
    metadata = get_request_metadata(request, client_data)
    
    image_data = None
    if image_file and image_file.filename:
        img_bytes = image_file.read(Config.MAX_FEEDBACK_IMAGE_SIZE + 1)
        if len(img_bytes) > Config.MAX_FEEDBACK_IMAGE_SIZE:
            raise BadRequest("Feedback image must be at most 256 KB")
        try:
            with Image.open(io.BytesIO(img_bytes)) as img:
                if img.format not in {"PNG", "JPEG", "WEBP"}:
                    raise ValueError("Unsupported image")
                mime_type = Image.MIME[img.format]
                img.verify()
        except Exception:
            raise BadRequest("Feedback must contain a valid PNG, JPEG or WebP image")
        image_data = f"data:{mime_type};base64,{base64.b64encode(img_bytes).decode('ascii')}"

    if message or image_data:
        log_feedback(device_id, message, image_data, metadata)
        
    return jsonify({"success": True, "message": "Feedback submitted successfully"})

@api_bp.route("/telemetry/event", methods=["POST"])
def log_client_event():
    device_id = get_device_id(request)
    data = json_object()
    
    event_type = data.get("event", "page_view")
    details = data.get("details", {})
    client_data = data.get("client_data", {})
    
    if not isinstance(event_type, str) or event_type not in {"page_view", "upload", "search", "feedback"} or not isinstance(details, dict) or not isinstance(client_data, dict):
        raise BadRequest("Invalid telemetry event")
    import json
    if len(json.dumps(data)) > 8000:
        raise BadRequest("Telemetry event too large")
    metadata = get_request_metadata(request, client_data)
    log_telemetry(event_type, device_id, details, metadata)
    
    return jsonify({"success": True})

# --- ADMIN ROUTES ---
def requires_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not Config.ADMIN_PASSWORD or not auth or auth.type != "basic" or not auth.password or not hmac.compare_digest(auth.password.encode(), Config.ADMIN_PASSWORD.encode()):
            return Response("Unauthorized", 401, {"WWW-Authenticate": 'Basic realm="Admin Access"'})
        return f(*args, **kwargs)
    return decorated

@api_bp.route("/dashboard")
@requires_admin
def admin_page():
    return render_template("admin.html")

@api_bp.route("/admin/api/data")
@requires_admin
def admin_data():
    import json
    telemetry = []
    feedback = []
    
    if kv_db:
        try:
            telemetry_raw = kv_db.lrange("telemetry_logs", 0, 49)
            telemetry = [json.loads(t) for t in telemetry_raw]
            
            feedback_raw = kv_db.lrange("feedback_logs", 0, 4)
            feedback = [json.loads(f) for f in feedback_raw]
        except Exception as e:
            logger.error(f"Vercel KV Load Error: {e}")
    else:
        if Config.TELEMETRY_DB_PATH.exists():
            try:
                with open(Config.TELEMETRY_DB_PATH, "r", encoding="utf-8") as f:
                    telemetry = json.load(f)[-50:][::-1]
            except Exception:
                pass
                
        if Config.FEEDBACK_DB_PATH.exists():
            try:
                with open(Config.FEEDBACK_DB_PATH, "r", encoding="utf-8") as f:
                    feedback = json.load(f)[-5:][::-1]
            except Exception:
                pass

    return jsonify({
        "success": True,
        "users": user_token_manager.get_all_users(),
        "telemetry": telemetry,
        "feedback": feedback 
    })

@api_bp.route("/admin/feedback/image/<filename>")
@requires_admin
def serve_feedback_image(filename):
    return send_from_directory(Config.FEEDBACK_DIR, filename)

@api_bp.route("/admin/api/user", methods=["POST"])
@requires_admin
def admin_action():
    data = json_object()
    device_id = data.get("device_id")
    action = data.get("action")

    if not isinstance(device_id, str) or not re.fullmatch(r"[a-f0-9]{16}|[a-f0-9]{32}", device_id):
        raise BadRequest("Invalid device ID")
    if not isinstance(action, str) or action not in {"reset", "set_limit"}:
        raise BadRequest("Invalid admin action")
    if action == "set_limit" and (type(data.get("limit")) is not int or not 0 <= data["limit"] <= 10_000_000):
        raise BadRequest("Limit must be an integer from 0 to 10000000")
    if action == "reset":
        user_token_manager.admin_update_user(device_id, new_used=0, new_limit=None)
    elif action == "set_limit":
        user_token_manager.admin_update_user(device_id, new_used=None, new_limit=int(data.get("limit", 20000)))

    return jsonify({"success": True})

@api_bp.route("/healthz")
def health():
    if kv_db:
        kv_db.ping()
    return jsonify(success=True, storage="redis" if kv_db else "local-development")
