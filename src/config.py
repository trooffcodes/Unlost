import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-brain-key")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
    
    # Filter out empty or unconfigured keys
    GROQ_KEYS = [k for k in [os.getenv("GROQ_API_KEY"), os.getenv("GROQ_API_KEY2")] if k]
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    
    GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    GEMINI_EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")

    IS_VERCEL = os.getenv("VERCEL") == "1" or os.getenv("VERCEL_ENV") is not None
    BASE_DIR = Path("/tmp") if IS_VERCEL else Path(__file__).resolve().parent
    
    # Storage Paths
    USER_DATA_DIR = BASE_DIR / "data" / "devices"
    DB_PATH = BASE_DIR / "data" / "vector_db.json"
    TOKEN_DB_PATH = BASE_DIR / "data" / "token_usage.json"
    TELEMETRY_DB_PATH = BASE_DIR / "data" / "telemetry.json"
    DEBUG_DIR = BASE_DIR / "debug_logs"
    FEEDBACK_DB_PATH = Path("data/feedback.json")
    FEEDBACK_DIR = Path("data/feedback_images")
    
    # Constraints
    MAX_FILE_SIZE = 15 * 1024 * 1024       # 15 MB
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100 MB max payload
    MAX_FILES_PER_BATCH = 50
    MAX_USER_TOKENS = 20_000
    
    ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    ALLOWED_PDF_EXT = {".pdf"}
    ALLOWED_TEXT_EXT = {".txt", ".md", ".csv", ".json", ".py", ".js", ".html", ".css", ".java", ".cpp", ".yml", ".yaml"}
    ALLOWED_ARCHIVE_EXT = {".zip"}
    
    ALLOWED_EXTENSIONS = ALLOWED_IMAGE_EXT | ALLOWED_PDF_EXT | ALLOWED_TEXT_EXT | ALLOWED_ARCHIVE_EXT

    @classmethod
    def init_dirs(cls):
        cls.USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        cls.DEBUG_DIR.mkdir(parents=True, exist_ok=True)

Config.init_dirs()