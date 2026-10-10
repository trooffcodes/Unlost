import hashlib
import shutil
import uuid
from pathlib import Path
from flask import Blueprint, jsonify, request, render_template, Response
from functools import wraps
from werkzeug.utils import secure_filename

from config import Config
from utils.logger import logger
from utils.telemetry import log_telemetry
from services.ai import generate_embedding
from services.vector_store import search_store, clear_user_data, get_user_files
from services.pipeline import queue_processing_batch, get_job_status
from services.token_manager import user_token_manager

api_bp = Blueprint("api", __name__)

def get_device_id(req) -> str:
    ip = req.headers.get("X-Forwarded-For", req.remote_addr) or "localhost"
    ua = req.headers.get("User-Agent", "generic_client")
    return hashlib.sha256(f"{ip}_{ua}".encode("utf-8")).hexdigest()[:16]

def make_safe_filename(original_name: str) -> str:
    safe = secure_filename(original_name)
    if not safe or safe.startswith("."):
        safe = f"doc_{uuid.uuid4().hex[:8]}{Path(original_name).suffix}"
    return safe

@api_bp.route("/")
def index():
    return render_template("index.html")

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
    return jsonify({"success": True, "data": user_token_manager.get_usage_stats(device_id)})

@api_bp.route("/clear_data", methods=["POST"])
def perform_clear_data():
    device_id = get_device_id(request)
    log_telemetry("clear_data", device_id)

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

    files_data = [(make_safe_filename(f.filename), f.read()) for f in files]

    try:
        batch_id = queue_processing_batch(device_id, files_data)
        return jsonify({"success": True, "batch_id": batch_id})
    except Exception as exc:
        logger.error(f"Upload initialization error: {exc}", exc_info=True)
        return jsonify({"success": False, "error": str(exc)}), 500

@api_bp.route("/status/<batch_id>", methods=["GET"])
def check_status(batch_id):
    status_data = get_job_status(batch_id)
    if status_data.get("status") == "not_found":
        return jsonify({"success": False, "error": "Job batch not found"}), 404
    return jsonify({"success": True, "data": status_data})

@api_bp.route("/search", methods=["POST"])
def search_documents():
    device_id = get_device_id(request)
    query = (request.get_json() or {}).get("query", "").strip()
    if not query:
        return jsonify({"success": False, "error": "Search query required"}), 400

    try:
        log_telemetry("search", device_id, {"query": query})
        query_embedding = generate_embedding(query)

        user_token_manager.track_usage(device_id, max(1, len(query) // 4))
        results = search_store(device_id, query_embedding)
        return jsonify({"success": True, "results": results})
    except Exception as exc:
        logger.error(f"Search API error: {exc}")
        return jsonify({"success": False, "error": "Search query failed"}), 500

@api_bp.route("/feedback", methods=["POST"])
def submit_feedback():
    device_id = get_device_id(request)
    data = request.json or {}
    message = data.get("message", "").strip()
    if message:
        log_telemetry("feedback", device_id, {"message": message})
    return jsonify({"success": True})

# --- ADMIN ROUTES ---
def requires_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or auth.password != Config.ADMIN_PASSWORD:
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
    telemetry = []
    if Config.TELEMETRY_DB_PATH.exists():
        try:
            import json
            with open(Config.TELEMETRY_DB_PATH, "r", encoding="utf-8") as f:
                telemetry = json.load(f)
        except Exception:
            pass

    return jsonify({
        "success": True,
        "users": user_token_manager.get_all_users(),
        "telemetry": telemetry[-50:][::-1]
    })

@api_bp.route("/admin/api/user", methods=["POST"])
@requires_admin
def admin_action():
    data = request.json or {}
    device_id = data.get("device_id")
    action = data.get("action")

    if action == "reset":
        user_token_manager.admin_update_user(device_id, new_used=0, new_limit=None)
    elif action == "set_limit":
        user_token_manager.admin_update_user(device_id, new_used=None, new_limit=int(data.get("limit", 20000)))

    return jsonify({"success": True})
