import json
import math
import threading
from typing import List, Dict, Any
from config import Config
from utils.logger import logger

db_lock = threading.Lock()

def _load_db() -> List[Dict[str, Any]]:
    if Config.DB_PATH.exists():
        try:
            with open(Config.DB_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load vector DB: {e}")
    return []

def _save_db(db: List[Dict[str, Any]]):
    try:
        with open(Config.DB_PATH, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to persist vector DB: {e}")

def add_to_store(user_id: str, filename: str, file_path: str, metadata: dict, embedding: List[float]):
    """Safely adds or updates document entries in the thread-safe JSON datastore."""
    with db_lock:
        db = _load_db()
        db = [doc for doc in db if not (doc.get("user_id") == user_id and doc.get("filename") == filename)]
        db.append({
            "user_id": user_id,
            "filename": filename,
            "file_path": file_path,
            "metadata": metadata or {},
            "embedding": embedding or []
        })
        _save_db(db)

def get_user_files(user_id: str) -> List[Dict[str, Any]]:
    """Retrieves all indexed user files, excluding vector embeddings to optimize bandwidth."""
    with db_lock:
        db = _load_db()

    return [
        {
            "filename": doc["filename"],
            "file_path": doc.get("file_path", ""),
            "folder": doc.get("metadata", {}).get("suggested_folder") or "Uncategorized",
            "summary": doc.get("metadata", {}).get("summary", ""),
            "tags": doc.get("metadata", {}).get("tags", []),
            "date": doc.get("metadata", {}).get("date", "Unknown"),
            "document_type": doc.get("metadata", {}).get("document_type", "Document")
        }
        for doc in db if doc.get("user_id") == user_id
    ]

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    mag1 = math.sqrt(sum(a * a for a in v1))
    mag2 = math.sqrt(sum(b * b for b in v2))
    return (dot / (mag1 * mag2)) if (mag1 > 0 and mag2 > 0) else 0.0

def search_store(user_id: str, query_embedding: List[float], top_k: int = 10) -> List[Dict[str, Any]]:
    if not query_embedding:
        return []

    with db_lock:
        db = _load_db()

    results = []
    for doc in db:
        if doc.get("user_id") != user_id:
            continue
        doc_emb = doc.get("embedding", [])
        if not doc_emb:
            continue

        sim = cosine_similarity(query_embedding, doc_emb)
        if sim > 0.25:
            results.append({
                "similarity": round(sim, 4),
                "filename": doc["filename"],
                "file_path": doc.get("file_path", ""),
                "metadata": doc.get("metadata", {})
            })

    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results[:top_k]

def clear_user_data(user_id: str):
    with db_lock:
        db = _load_db()
        filtered = [doc for doc in db if doc.get("user_id") != user_id]
        if len(filtered) != len(db):
            _save_db(filtered)
