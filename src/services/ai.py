import json
import time
import base64
import mimetypes
import threading
import re
import requests
from typing import Dict, Any, List
from pathlib import Path

from config import Config
from utils.logger import logger, time_it

GROQ_SYSTEM_PROMPT = """You are an expert document metadata extractor. You will receive OCR/plain text.
If the text contains insufficient signal to classify the file, return EXACTLY: {"sufficient": false}

If sufficient, return a valid JSON object matching this schema:
{
  "sufficient": true,
  "document_title": "Concise document title",
  "document_type": "Invoice | Receipt | Source Code | Notes | Documentation | Identity | Other",
  "suggested_folder": "Categorical folder name (e.g. Finances, Architecture, Notes)",
  "total_amount": null,
  "currency": null,
  "date": "YYYY-MM-DD or null",
  "tags": ["tag1", "tag2", "tag3"],
  "summary": "Concise two-sentence summary.",
  "semantic_search_text": "Dense keyword and contextual summary string for vector embedding"
}
Output valid JSON only with no markdown formatting."""

GEMINI_SYSTEM_PROMPT = """Analyze this document visually and return pure JSON only matching this schema:
{
  "document_title": "Concise document title",
  "document_type": "Invoice | Receipt | Document | Image | Other",
  "suggested_folder": "Logical folder name",
  "total_amount": null,
  "currency": null,
  "date": "YYYY-MM-DD or null",
  "tags": ["tag1", "tag2", "tag3"],
  "summary": "Concise two-sentence summary.",
  "semantic_search_text": "Dense keyword and contextual summary string for vector embedding"
}
Output valid JSON only with no markdown formatting."""

class GroqTokenManager:
    def __init__(self, keys: List[str], max_tpm: int = 7500):
        self.keys = [k for k in keys if k]
        self.max_tpm = max_tpm
        self.lock = threading.Lock()
        self.usage = {key: [] for key in self.keys}

    def get_key(self, estimated_tokens: int = 3500) -> str | None:
        with self.lock:
            now = time.time()
            for key in self.keys:
                self.usage[key] = [(ts, tk) for ts, tk in self.usage[key] if now - ts < 60]
                current_tokens = sum(tk for ts, tk in self.usage[key])
                if current_tokens + estimated_tokens < self.max_tpm:
                    return key
            return None

    def record_usage(self, key: str, tokens: int):
        if not key:
            return
        with self.lock:
            self.usage.setdefault(key, []).append((time.time(), tokens))

    def penalize_key(self, key: str):
        if not key:
            return
        with self.lock:
            self.usage.setdefault(key, []).append((time.time(), self.max_tpm))

groq_manager = GroqTokenManager(Config.GROQ_KEYS)

def _clean_json_markdown(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    return cleaned.strip()

def _call_groq(ocr_text: str, filename: str) -> Dict[str, Any]:
    trimmed_text = ocr_text[:12000]
    payload = {
        "model": Config.GROQ_MODEL,
        "messages": [
            {"role": "system", "content": GROQ_SYSTEM_PROMPT},
            {"role": "user", "content": f"Filename: {filename}\n\nContent:\n{trimmed_text}"}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1
    }

    for _ in range(max(1, len(groq_manager.keys))):
        key = groq_manager.get_key()
        if not key:
            break
        try:
            res = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
                timeout=25
            )
            res.raise_for_status()
            data = res.json()
            tokens = data.get("usage", {}).get("total_tokens", 1000)
            groq_manager.record_usage(key, tokens)
            return json.loads(_clean_json_markdown(data["choices"][0]["message"]["content"]))
        except Exception as e:
            logger.warning(f"Groq API error on key ending in ...{key[-4:]}: {e}")
            groq_manager.penalize_key(key)

    raise RuntimeError("All Groq keys unavailable or exhausted.")

def _call_gemini_vision(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    if not Config.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not configured.")

    mime_type, _ = mimetypes.guess_type(filename)
    mime_type = mime_type or ("application/pdf" if filename.lower().endswith(".pdf") else "image/jpeg")
    b64_data = base64.b64encode(file_bytes).decode("utf-8")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{Config.GEMINI_MODEL}:generateContent?key={Config.GEMINI_API_KEY}"
    payload = {
        "systemInstruction": {"parts": [{"text": GEMINI_SYSTEM_PROMPT}]},
        "contents": [{
            "role": "user",
            "parts": [
                {"text": f"Analyze file '{filename}' and produce structured metadata."},
                {"inlineData": {"mimeType": mime_type, "data": b64_data}}
            ]
        }],
        "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"}
    }

    res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=45)
    res.raise_for_status()
    raw = res.json()["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(_clean_json_markdown(raw))

@time_it
def generate_embedding(text: str) -> List[float]:
    """Generates standard dense embeddings using Google Gemini."""
    if not text:
        return []

    clean_text = text[:8000].strip()
    if not Config.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not configured.")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{Config.GEMINI_EMBEDDING_MODEL}:embedContent?key={Config.GEMINI_API_KEY}"
    payload = {
        "model": f"models/{Config.GEMINI_EMBEDDING_MODEL}",
        "content": {"parts": [{"text": clean_text}]}
    }
    
    # We remove the silent try/except block. If rate limited, it needs to throw an error 
    # so we don't accidentally save empty vectors to the database.
    res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=15)
    res.raise_for_status() 
    
    values = res.json().get("embedding", {}).get("values", [])
    if values:
        return values
        
    raise ValueError("Gemini API returned success but empty embedding values.")

@time_it
def extract_semantic_metadata(file_bytes: bytes, filename: str, text_content: str) -> Dict[str, Any]:
    """Attempts fast Groq processing, falls back to Gemini Vision, and defaults to heuristic metadata."""
    default_meta = {
        "document_title": filename.rsplit(".", 1)[0].replace("_", " ").title(),
        "document_type": "Document",
        "suggested_folder": "General",
        "total_amount": None,
        "currency": None,
        "date": time.strftime("%Y-%m-%d"),
        "tags": [Path(filename).suffix.lstrip(".").lower()],
        "summary": text_content[:200] if text_content else "Uploaded file.",
        "semantic_search_text": f"{filename} {text_content[:1000]}"
    }

    if text_content and len(text_content.strip()) >= 20:
        try:
            groq_res = _call_groq(text_content, filename)
            if groq_res.get("sufficient") is not False:
                groq_res.pop("sufficient", None)
                default_meta.update({k: v for k, v in groq_res.items() if v is not None})
                return default_meta
        except Exception as e:
            logger.info(f"Groq bypassed or failed for {filename}: {e}. Trying Gemini Vision...")

    if Config.GEMINI_API_KEY and len(file_bytes) > 0:
        try:
            gemini_res = _call_gemini_vision(file_bytes, filename)
            default_meta.update({k: v for k, v in gemini_res.items() if v is not None})
            return default_meta
        except Exception as e:
            logger.warning(f"Gemini Vision failed for {filename}: {e}")

    return default_meta