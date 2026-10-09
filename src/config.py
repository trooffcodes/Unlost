import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class Config:
    UPLOAD_FOLDER = Path("uploads")
    DEBUG_DIR = Path("debug_logs")
    
    # API Keys
    GROQ_KEYS = [key for key in [os.getenv("GROQ"), os.getenv("GROQ2")] if key]
    GEMINI_API_KEY = os.getenv("GEMINI", "")
    OCR_SPACE_KEY = os.getenv("OCR_SPACE_KEY", "")
    LLAMA_CLOUD_API_KEY = os.getenv("LLAMA_CLOUD_API_KEY") or os.getenv("LlamaParse", "")
    
    # Models
    GROQ_MODEL = "qwen/qwen3.8-27b"
    GEMINI_MODEL = "gemini-3.5-flash-lite"
    
    # File Constraints
    MAX_FILE_SIZE = 5 * 1024 * 1024 # 5MB
    ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tiff", ".bmp"}
    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

Config.UPLOAD_FOLDER.mkdir(exist_ok=True)
Config.DEBUG_DIR.mkdir(exist_ok=True)