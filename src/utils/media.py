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
        img = img.convert("L")  # Grayscale
        
        contrast_enhancer = ImageEnhance.Contrast(img)
        img = contrast_enhancer.enhance(1.5)
        
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
        logger.warning(f"OCR compression failed, returning original bytes: {e}")
        return file_bytes

@time_it
def compress_for_llm(file_bytes: bytes, suffix: str, max_dimension: int = 1024) -> bytes:
    """Reduces resolution to save visual tokens in LLMs without losing layout context."""
    if suffix.lower() == ".pdf":
        return file_bytes
        
    try:
        img = Image.open(io.BytesIO(file_bytes))
        # Resize to max dimensions to drastically reduce token count
        img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
        
        out_io = io.BytesIO()
        img.save(out_io, format="JPEG", quality=85)
        optimized_bytes = out_io.getvalue()
        
        logger.info(f"LLM Image optimization: reduced from {len(file_bytes)/1024:.1f}KB to {len(optimized_bytes)/1024:.1f}KB")
        return optimized_bytes
    except Exception as e:
        logger.warning(f"LLM compression failed, returning original bytes: {e}")
        return file_bytes