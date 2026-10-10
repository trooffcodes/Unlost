import json
import time
import threading
from config import Config
from utils.logger import logger

# Prevent file corruption via simultaneous write threads
telemetry_lock = threading.Lock()

def log_telemetry(event_type: str, device_id: str, details: dict = None):
    if details is None:
        details = {}
        
    entry = {
        "timestamp": time.time(),
        "event": event_type,
        "device_id": device_id,
        "details": details
    }
    
    logger.info(f"TELEMETRY [{event_type}] | Device: {device_id} | Details: {details}")
    
    try:
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