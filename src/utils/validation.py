import io
import filetype
from hashlib import sha256
from pathlib import Path
from PIL import Image
from config import Config

def _get_hash(data: bytes) -> str:
    return sha256(data).hexdigest()

def validate_upload(file_bytes: bytes, filename: str, upload_folder: Path | None) -> str | None:
    if not file_bytes or not filename:
        return "No file selected"
    if len(file_bytes) == 0:
        return "File is empty"
    if len(file_bytes) > Config.MAX_FILE_SIZE:
        max_mb = Config.MAX_FILE_SIZE // (1024 * 1024)
        return f"File is too large (Max: {max_mb}MB)"

    suffix = Path(filename).suffix.lower()
    if suffix not in Config.ALLOWED_EXTENSIONS:
        return "Invalid file type extension"

    if suffix not in Config.ALLOWED_TEXT_EXT:
        kind = filetype.guess(file_bytes)
        if not kind or f".{kind.extension}" not in Config.ALLOWED_EXTENSIONS:
            return "File content does not match allowed types"

    if suffix in Config.ALLOWED_IMAGE_EXT:
        try:
            with Image.open(io.BytesIO(file_bytes)) as img:
                img.verify()
        except Exception:
            return "File appears to be corrupted"
 
    target_hash = _get_hash(file_bytes)
    target_size = len(file_bytes)
    
    if upload_folder and upload_folder.exists():
        for existing in upload_folder.rglob("*"):
            if existing.is_file():
                try:
                    if existing.stat().st_size == target_size:
                        if _get_hash(existing.read_bytes()) == target_hash:
                            return f"Duplicate file! Already uploaded as {existing.name}"
                except Exception:
                    pass

    return None