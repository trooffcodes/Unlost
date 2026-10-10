import io
from PIL import Image, ImageEnhance, ImageFilter
from utils.logger import logger, time_it

@time_it
def compress_for_ocr(file_bytes: bytes, suffix: str, max_bytes: int = 1_000_000) -> bytes:
    """Optimizes image specifically for OCR (Grayscale, high contrast, sharp)."""
    if suffix.lower() == ".pdf":
        return file_bytes

    try:
        img = Image.open(io.BytesIO(file_bytes))
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        img.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
        img = img.convert("L")
        
        img = ImageEnhance.Contrast(img).enhance(1.5)
        img = img.filter(ImageFilter.SHARPEN)
        
        quality = 95
        out_io = io.BytesIO()
        while True:
            out_io.seek(0)
            out_io.truncate(0)
            img.save(out_io, format="JPEG", quality=quality)
            if out_io.tell() <= max_bytes or quality <= 10:
                break
            quality -= 15
            
        return out_io.getvalue()
    except Exception as e:
        logger.warning(f"OCR compression failed: {e}. Returning raw bytes.")
        return file_bytes

@time_it
def compress_for_llm(file_bytes: bytes, suffix: str, max_dimension: int = 1024) -> bytes:
    if suffix.lower() == ".pdf":
        return file_bytes
        
    try:
        img = Image.open(io.BytesIO(file_bytes))
        # CRITICAL FIX: Safe conversion handling prior to LA fallback processing
        if img.mode in ("RGBA", "P", "LA"):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'RGBA' or img.mode == 'LA':
                background.paste(img, mask=img.split()[-1])
                img = background
            else:
                img = img.convert("RGB")

        img = img.convert("RGB")
        img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
        out_io = io.BytesIO()
        img.save(out_io, format="JPEG", quality=85)
        return out_io.getvalue()
    except Exception as e:
        logger.warning(f"LLM image compression failed: {e}. Returning raw bytes.")
        return file_bytes