import os
import logging
import time
from functools import wraps
from pathlib import Path

IS_VERCEL = os.getenv("VERCEL") == "1" or os.getenv("VERCEL_ENV") is not None
LOG_FILE = Path("/tmp/app.log") if IS_VERCEL else Path("app.log")

logger = logging.getLogger("AppLogger")
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(threadName)s | %(module)s | %(message)s')

if logger.hasHandlers():
    logger.handlers.clear()

try:
    if not IS_VERCEL:
        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
except Exception:
    pass

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# --- IN-MEMORY LOG BUFFER FOR WEBHOOK ---
class WebhookLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.buffer = []
        self.buffer_size = 0
        self.max_size = 250 * 1024 # 250 KB limit
        self._is_flushing = False

    def emit(self, record):
        try:
            msg = self.format(record) + "\n"
            msg_bytes = msg.encode('utf-8')
            self.buffer.append(msg_bytes)
            self.buffer_size += len(msg_bytes)
            
            is_error = record.levelno >= logging.ERROR
            
            if is_error or self.buffer_size >= self.max_size:
                self.flush_logs(reason="Error Encountered" if is_error else "Size Limit Reached (250KB)")
        except Exception:
            pass
            
    def flush_logs(self, reason="Manual"):
        if getattr(self, '_is_flushing', False):
            return
        self._is_flushing = True
        try:
            if not self.buffer:
                return
            
            from config import Config
            if not Config.WEBHOOK_LOGS:
                return
                
            import requests
            
            log_data = b"".join(self.buffer)
            self.buffer = []
            self.buffer_size = 0
            
            # Use strict timeout constraints
            requests.post(
                Config.WEBHOOK_LOGS,
                data={"content": f"📜 **Debug Logs Triggered**\n**Reason:** {reason}\n**Size:** {len(log_data)/1024:.2f} KB"},
                files={"file": ("debug.log", log_data)},
                timeout=12
            )
        except Exception:
            pass
        finally:
            self._is_flushing = False

webhook_log_handler = WebhookLogHandler()
webhook_log_handler.setFormatter(formatter)
logger.addHandler(webhook_log_handler)

class DiscordErrorHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self._is_emitting = False

    def emit(self, record):
        if getattr(self, '_is_emitting', False):
            return
        self._is_emitting = True
        try:
            if record.levelno >= logging.ERROR:
                from utils.webhook import notify_error
                notify_error(self.format(record))
        except Exception:
            pass
        finally:
            self._is_emitting = False

discord_handler = DiscordErrorHandler()
discord_handler.setFormatter(formatter)
logger.addHandler(discord_handler)

def time_it(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        logger.debug(f"[{func.__name__}] Starting execution...")
        try:
            result = func(*args, **kwargs)
            elapsed = time.perf_counter() - start
            logger.info(f"[{func.__name__}] Execution completed in {elapsed:.4f}s")
            return result
        except Exception as e:
            elapsed = time.perf_counter() - start
            logger.error(f"[{func.__name__}] Failed after {elapsed:.4f}s with error: {str(e)}")
            raise
    return wrapper