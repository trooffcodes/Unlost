import json
import time
import threading
import uuid
from config import Config, kv_db
from user_agents import parse
from utils.logger import logger

telemetry_lock = threading.Lock()
feedback_lock = threading.Lock()

def log_telemetry(event_type: str, device_id: str, details: dict = None, metadata: dict = None):
    if details is None: details = {}
    if metadata is None: metadata = {}

    entry = {
        "timestamp": time.time(),
        "event": event_type,
        "device_id": device_id,
        "details": details,
        "metadata": metadata
    }
    logger.info(f"TELEMETRY [{event_type}] | Device: {device_id} | Details: {details}")

    try:
        if kv_db:
            kv_db.lpush("telemetry_logs", json.dumps(entry))
            kv_db.ltrim("telemetry_logs", 0, 999)
        else:
            with telemetry_lock:
                logs = []
                if Config.TELEMETRY_DB_PATH.exists():
                    with open(Config.TELEMETRY_DB_PATH, "r", encoding="utf-8") as f:
                        logs = json.load(f)
                logs.append(entry)
                with open(Config.TELEMETRY_DB_PATH, "w", encoding="utf-8") as f:
                    json.dump(logs[-1000:], f, indent=2)
    except Exception as e:
        logger.error(f"Failed to log telemetry: {e}")

def log_feedback(device_id: str, message: str, image_data: str = None, metadata: dict = None):
    if metadata is None: metadata = {}

    entry = {
        "id": uuid.uuid4().hex[:8],
        "timestamp": time.time(),
        "device_id": device_id,
        "message": message,
        "image_data": image_data,
        "status": "new",
        "metadata": metadata
    }
    logger.info(f"FEEDBACK | Device: {device_id} | Msg: {message[:20]}... | Meta: {metadata}")

    try:
        if kv_db:
            kv_db.lpush("feedback_logs", json.dumps(entry))
            kv_db.ltrim("feedback_logs", 0, 499)
        else:
            with feedback_lock:
                feedbacks = []
                if Config.FEEDBACK_DB_PATH.exists():
                    with open(Config.FEEDBACK_DB_PATH, "r", encoding="utf-8") as f:
                        feedbacks = json.load(f)
                feedbacks.append(entry)
                with open(Config.FEEDBACK_DB_PATH, "w", encoding="utf-8") as f:
                    json.dump(feedbacks[-500:], f, indent=2)
    except Exception as e:
        logger.error(f"Failed to log feedback: {e}")

def get_request_metadata(req, client_data: dict = None) -> dict:
    if client_data is None: client_data = {}

    ip_address = req.headers.get("X-Forwarded-For", req.remote_addr) or "localhost"
    ip_address = ip_address.split(',')[0].strip() # Isolate real IP
    ua_string = req.headers.get("User-Agent", "generic_client")

    user_agent = parse(ua_string)
    device_type = "Mobile" if user_agent.is_mobile else "Tablet" if user_agent.is_tablet else "PC"

    return {
        "ip_address": ip_address,
        "os": f"{user_agent.os.family} {user_agent.os.version_string}",
        "browser": f"{user_agent.browser.family} {user_agent.browser.version_string}",
        "device_type": device_type,
        "raw_user_agent": ua_string,
        "resolution": client_data.get("resolution", "Unknown"),
        "time_on_page": client_data.get("time_on_page", "Unknown"),
        "current_url": client_data.get("current_url", "Unknown")
    }
