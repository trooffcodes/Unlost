import os
import redis
import secrets
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

kv_url = os.environ.get("KV_URL") or os.environ.get("REDIS_URL")
kv_db = redis.Redis.from_url(kv_url, decode_responses=True, socket_connect_timeout=5, socket_timeout=5, health_check_interval=30) if kv_url else None

class Config:
    # --- WEBHOOK CONFIGURATION ---
    WEBHOOK_FEEDBACK = os.getenv("WEBHOOK_FEEDBACK")
    WEBHOOK_USER = os.getenv("WEBHOOK_USER")
    WEBHOOK_FILE = os.getenv("WEBHOOK_FILE")
    WEBHOOK_ERROR = os.getenv("WEBHOOK_ERROR")
    # -----------------------------

    SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_hex(32)
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
    
    GROQ_KEYS = [k for k in [os.getenv("GROQ_API_KEY"), os.getenv("GROQ_API_KEY2")] if k]
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    OCR_SPACE_KEY = os.getenv("OCR_SPACE_KEY")
    LLAMA_CLOUD_API_KEY = os.getenv("LLAMA_CLOUD_API_KEY") or os.getenv("LlamaParse")
    
    GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    GEMINI_EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")

    IS_VERCEL = os.getenv("VERCEL") == "1" or os.getenv("VERCEL_ENV") is not None
    GEMINI_BASE_URL = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
    GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
    BASE_DIR = Path("/tmp") if IS_VERCEL else Path(__file__).resolve().parent
    
    USER_DATA_DIR = BASE_DIR / "data" / "devices"
    DB_PATH = BASE_DIR / "data" / "vector_db.json"
    TOKEN_DB_PATH = BASE_DIR / "data" / "token_usage.json"
    TELEMETRY_DB_PATH = BASE_DIR / "data" / "telemetry.json"
    DEBUG_DIR = BASE_DIR / "debug_logs"
    FEEDBACK_DB_PATH = BASE_DIR / "data" / "feedback.json"
    FEEDBACK_DIR = BASE_DIR / "data" / "feedback_images"
    
    MAX_FILE_SIZE = (4_000_000 if IS_VERCEL else 15 * 1024 * 1024)
    MAX_CONTENT_LENGTH = (4_200_000 if IS_VERCEL else 100 * 1024 * 1024)
    MAX_FILES_PER_BATCH = 1 if IS_VERCEL else 50
    MAX_EXPANDED_BYTES = 30 * 1024 * 1024
    MAX_FEEDBACK_IMAGE_SIZE = 256 * 1024
    MAX_LIBRARY_FILES = 200
    MAX_USER_TOKENS = 20_000
    
    ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    ALLOWED_PDF_EXT = {".pdf"}
    ALLOWED_TEXT_EXT = {".txt", ".md", ".csv", ".json", ".py", ".js", ".html", ".css", ".java", ".cpp", ".yml", ".yaml"}
    ALLOWED_ARCHIVE_EXT = {".zip"}
    
    ALLOWED_EXTENSIONS = ALLOWED_IMAGE_EXT | ALLOWED_PDF_EXT | ALLOWED_TEXT_EXT | ALLOWED_ARCHIVE_EXT

    @classmethod
    def init_dirs(cls):
        for d in [cls.USER_DATA_DIR, cls.DB_PATH.parent, cls.DEBUG_DIR, cls.FEEDBACK_DIR]:
            try:
                d.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass 

if Config.IS_VERCEL:
    missing = [name for name in ("SECRET_KEY", "GEMINI_API_KEY") if not os.getenv(name)]
    if not kv_url:
        missing.append("REDIS_URL (or KV_URL)")
    if missing:
        raise RuntimeError("Missing required production configuration: " + ", ".join(missing))
    if len(Config.SECRET_KEY) < 32:
        raise RuntimeError("SECRET_KEY must contain at least 32 characters")

Config.init_dirs()
