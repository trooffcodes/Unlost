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
        expected = ".jpg" if suffix == ".jpeg" else suffix
        if not kind or f".{kind.extension}" != expected:
            return "File content does not match its extension"

    if suffix in Config.ALLOWED_IMAGE_EXT:
        try:
            with Image.open(io.BytesIO(file_bytes)) as img:
                if img.width * img.height > 20_000_000:
                    return "Image exceeds 20 megapixels"
                img.verify()
        except Exception:
            return "File appears to be corrupted"
 
    if suffix == ".pdf":
        try:
            import fitz
            with fitz.open(stream=file_bytes, filetype="pdf") as document:
                if document.needs_pass or not 1 <= len(document) <= 100:
                    return "PDF must be unencrypted and contain 1 to 100 pages"
        except Exception:
            return "PDF appears to be corrupted"
    return None
