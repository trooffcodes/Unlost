import json
import time
import base64
import mimetypes
import threading
import requests
from typing import Dict, Any

from config import Config
from utils.logger import logger, time_it

# Prompts
GROQ_SYSTEM_PROMPT = """You are an expert document metadata extractor. You will receive OCR text.
First, analyze if the OCR text is sufficient to extract meaningful file metadata.
If completely insufficient, return EXACTLY: {"sufficient": false}

If sufficient, return a STRICT JSON object representing the document:
{
  "sufficient": true,
  "document_title": "String - Generated title",
  "document_type": "String",
  "suggested_folder": "String",
  "total_amount": "Number or null",
  "currency": "String (3 letters) or null",
  "date": "YYYY-MM-DD or null",
  "tags": ["Array", "of", "3-5", "tags"],
  "summary": "String - Concise 2-sentence summary",
  "semantic_search_text": "String - Dense block of text for vector DB"
}
Output nothing but valid JSON."""

GEMINI_SYSTEM_PROMPT = """You are a multimodal document metadata extractor.
Analyze the document visually and return EXACTLY this JSON:
{
  "document_title": "String",
  "document_type": "String",
  "suggested_folder": "String",
  "total_amount": "Number or null",
  "currency": "String or null",
  "date": "YYYY-MM-DD or null",
  "tags": ["Array", "of", "tags"],
  "summary": "String",
  "semantic_search_text": "String"
}"""


class GroqTokenManager:
    """Manages rate limits for multiple Groq API keys (8K tokens / min)."""
    def __init__(self, keys, max_tpm=7800):
        self.keys = keys
        self.max_tpm = max_tpm
        self.lock = threading.Lock()
        self.usage = {key: [] for key in keys}

    def get_key(self, estimated_tokens=4000):
        with self.lock:
            now = time.time()
            for key in self.keys:
                self.usage[key] = [(ts, tk) for ts, tk in self.usage[key] if now - ts < 60]
                current_tokens = sum(tk for ts, tk in self.usage[key])
                
                if current_tokens + estimated_tokens < self.max_tpm:
                    return key
                    
            return None 

    def record_usage(self, key, tokens):
        with self.lock:
            self.usage[key].append((time.time(), tokens))
            logger.info(f"Groq token usage recorded: {tokens} on key ...{key[-4:]}")


groq_manager = GroqTokenManager(Config.GROQ_KEYS)

def _save_debug_output(filename: str, source: str, data: Dict[str, Any]):
    try:
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        safe_name = filename.replace(" ", "_").split(".")[0]
        debug_file = Config.DEBUG_DIR / f"{safe_name}_{source}_{timestamp}.json"
        with open(debug_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to save debug for {filename}: {e}")

def _is_ocr_insufficient(ocr_text: str) -> bool:
    if not ocr_text:
        return True
    clean_text = ocr_text.strip()
    if len(clean_text) < 15:
        return True
    alnum = sum(c.isalnum() for c in clean_text)
    return (alnum / max(len(clean_text), 1)) < 0.35

def _call_groq_qwen(ocr_text: str, filename: str) -> Dict[str, Any]:
    MAX_CHARS = 14000
    if len(ocr_text) > MAX_CHARS:
        logger.warning(f"[{filename}] OCR text truncated to prevent Groq Rate Limit.")
        ocr_text = ocr_text[:MAX_CHARS]

    api_key = groq_manager.get_key(estimated_tokens=5000)
    
    if not api_key:
        logger.warning(f"[{filename}] All Groq keys rate-limited. Forcing Gemini fallback.")
        raise ValueError("Groq Rate Limit Reached")

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    
    payload = {
        "model": Config.GROQ_MODEL,
        "messages": [
            {"role": "system", "content": GROQ_SYSTEM_PROMPT},
            {"role": "user", "content": f"OCR TEXT:\n{ocr_text}"} 
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1
    }
    
    start = time.time()
    response = requests.post(url, headers=headers, json=payload, timeout=20)
    response.raise_for_status()

    data = response.json()
    tokens_used = data.get("usage", {}).get("total_tokens", 0)
    groq_manager.record_usage(api_key, tokens_used)
    
    return json.loads(data["choices"][0]["message"]["content"])


def _call_gemini_vision(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{Config.GEMINI_MODEL}:generateContent?key={Config.GEMINI_API_KEY}"
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    base64_data = base64.b64encode(file_bytes).decode("utf-8")
    
    payload = {
        "systemInstruction": {"parts": [{"text": GEMINI_SYSTEM_PROMPT}]},
        "contents": [{
            "role": "user",
            "parts": [
                {"text": "Analyze this file visually and extract metadata."},
                {"inlineData": {"mimeType": mime_type, "data": base64_data}}
            ]
        }],
        "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"}
    }
    
    response = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=60)
    response.raise_for_status()
    
    data = response.json()
    result_text = data["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(result_text)

@time_it
def generate_embedding(text: str) -> list[float]:
    """Generates semantic embedding for dense search strings using Gemini."""
    if not text:
        return []
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={Config.GEMINI_API_KEY}"
    payload = {"content": {"parts": [{"text": text}]}}
    
    try:
        response = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
        response.raise_for_status()
        return response.json().get("embedding", {}).get("values", [])
    except Exception as e:
        logger.error(f"Failed to generate embedding: {e}")
        return []

@time_it
def extract_semantic_metadata(file_bytes: bytes, filename: str, ocr_text: str) -> Dict[str, Any]:
    default_meta = {
        "document_title": "Unknown Document", "document_type": "Unknown", "suggested_folder": "Uncategorized",
        "total_amount": None, "currency": None, "date": None, "tags": [],
        "summary": "Analysis failed or unavailable.", "semantic_search_text": ""
    }
    
    if not _is_ocr_insufficient(ocr_text):
        try:
            qwen_res = _call_groq_qwen(ocr_text, filename)
            _save_debug_output(filename, "qwen", qwen_res)
            if qwen_res.get("sufficient") is True:
                qwen_res.pop("sufficient", None)
                default_meta.update(qwen_res)
                return default_meta
        except Exception as e:
            logger.error(f"[{filename}] Groq AI failed: {e}. Falling back...")

    try:
        gemini_res = _call_gemini_vision(file_bytes, filename)
        _save_debug_output(filename, "gemini", gemini_res)
        default_meta.update(gemini_res)
    except Exception as e:
        default_meta["summary"] = f"Extraction failed: {str(e)}"
        
    return default_meta