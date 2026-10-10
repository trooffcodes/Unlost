import os
import logging
import time
from functools import wraps
from pathlib import Path

logger = logging.getLogger("AppLogger")
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(threadName)s | %(module)s | %(message)s')

IS_VERCEL = os.getenv("VERCEL") == "1" or os.getenv("VERCEL_ENV") is not None
LOG_FILE = Path("/tmp/app.log") if IS_VERCEL else Path("app.log")

try:
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
except Exception:
    pass

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

class DiscordErrorHandler(logging.Handler):
    def emit(self, record):
        if record.levelno >= logging.ERROR:
            try:
                from utils.webhook import notify_error
                # Exceptions may contain credentials, document text or signed URLs.
                notify_error(f"{record.module}: {record.levelname}. Check application logs for details.")
            except Exception:
                pass


logger.addHandler(DiscordErrorHandler())


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
            logger.error(f"[{func.__name__}] Failed after {elapsed:.4f}s with error: {type(e).__name__}")
            raise
    return wrapper