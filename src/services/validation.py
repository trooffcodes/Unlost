from pathlib import Path
from hashlib import sha256

import filetype
from PIL import Image

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB limit
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf"}

def get_file_hash(file_stream) -> str:
    """Generate a SHA-256 hash of the file stream to detect duplicates."""
    hasher = sha256()
    for chunk in iter(lambda: file_stream.read(4096), b""):
        hasher.update(chunk)
    file_stream.seek(0)
    return hasher.hexdigest()

def check_file_presence(file) -> tuple[bool, str | None]:
    """Ensures a file was provided and has a filename."""
    if not file or file.filename == "":
        return False, "No file selected"
    return True, None

def check_file_size(file) -> tuple[bool, str | None]:
    """Validates that the file is not empty and within size limits."""
    file.stream.seek(0, 2)
    file_size = file.stream.tell()
    file.stream.seek(0)

    if file_size == 0:
        return False, "File is empty"
    if file_size > MAX_FILE_SIZE:
        return False, "File is too large (Max size: 5MB)"
        
    return True, None

def check_file_type(file) -> tuple[bool, str | None]:
    """Validates file extension and inspects magic bytes."""
    original_filename = file.filename or ""
    suffix = Path(original_filename).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        return False, "Invalid file type extension"

    kind = filetype.guess(file.stream)
    file.stream.seek(0)
    if not kind or f".{kind.extension}" not in ALLOWED_EXTENSIONS:
        return False, "File content does not match allowed types"
        
    return True, None

def check_file_corruption(file) -> tuple[bool, str | None]:
    """Verifies that image files are uncorrupted."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg"}:
        try:
            img = Image.open(file.stream)
            img.verify()
            file.stream.seek(0)
        except Exception:
            return False, "File appears to be corrupted or invalid"
            
    return True, None

def check_duplicate(file, upload_folder: Path) -> tuple[bool, str | None]:
    """Checks if identical content already exists in the upload folder."""
    file_hash = get_file_hash(file.stream)
    
    for existing_file in upload_folder.iterdir():
        if existing_file.is_file():
            with open(existing_file, "rb") as f:
                if sha256(f.read()).hexdigest() == file_hash:
                    return False, f"Duplicate file detected! Already uploaded as {existing_file.name}"
                    
    return True, None