import io
from PIL import Image, ImageEnhance, ImageFilter

def compress_file(file_bytes: bytes, suffix: str, max_bytes: int = 1_000_000) -> bytes:
    """Optimizes and compresses an image specifically for OCR processing."""
    if suffix.lower() == ".pdf":
        return file_bytes

    img = Image.open(io.BytesIO(file_bytes))
    
    # 1. Convert to Grayscale 
    # Drops unnecessary color channels, reducing file size and focusing on luminance
    img = img.convert("L")
    
    # 2. Enhance Contrast 
    # Makes dark text darker and light backgrounds lighter
    contrast_enhancer = ImageEnhance.Contrast(img)
    img = contrast_enhancer.enhance(1.5)  # Boost contrast by 50%
    
    # 3. Apply Sharpening Filter 
    # Crisps up the edges of the text letters so the OCR engine can read them better
    img = img.filter(ImageFilter.SHARPEN)
    
    # 4. Compress to fit API limits
    quality = 95
    out_io = io.BytesIO()
    
    while True:
        out_io.seek(0)
        out_io.truncate(0)
        # JPEG handles grayscale well and allows aggressive size reduction
        img.save(out_io, format="JPEG", quality=quality)
        
        if out_io.tell() <= max_bytes or quality <= 10:
            break
        quality -= 15 
        
    return out_io.getvalue()