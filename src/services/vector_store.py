import json
import math
import threading
from typing import List, Dict, Any
from config import Config, kv_db
from utils.logger import logger

db_lock = threading.Lock()

def _load_user_db(user_id: str) -> List[Dict[str, Any]]:
    if kv_db:
        try:
            data = kv_db.get(f"vector_db:{user_id}")
            return json.loads(data) if data else []
        except Exception as e:
            logger.error(f"KV Load Error: {e}")
            return []

    if Config.DB_PATH.exists():
        try:
            with open(Config.DB_PATH, "r", encoding="utf-8") as f:
                db = json.load(f)
                return [doc for doc in db if doc.get("user_id") == user_id]
        except Exception as e:
            logger.error(f"DB Load Error: {e}")
    return []

def _save_user_db(user_id: str, user_db: List[Dict[str, Any]]):
    if kv_db:
        try:
            kv_db.set(f"vector_db:{user_id}", json.dumps(user_db))
            return
        except Exception as e:
            logger.error(f"KV Save Error: {e}")

    with db_lock:
        db = []
        if Config.DB_PATH.exists():
            try:
                with open(Config.DB_PATH, "r", encoding="utf-8") as f:
                    db = json.load(f)
            except Exception:
                pass
        db = [doc for doc in db if doc.get("user_id") != user_id]
        db.extend(user_db)
        try:
            with open(Config.DB_PATH, "w", encoding="utf-8") as f:
                json.dump(db, f, indent=2)
        except Exception as e:
            logger.error(f"DB Save Error: {e}")

def add_to_store(user_id: str, filename: str, file_path: str, metadata: dict, embedding: List[float]):
    db = _load_user_db(user_id)
    db = [doc for doc in db if doc.get("filename") != filename]
    db.append({
        "user_id": user_id,
        "filename": filename,
        "file_path": file_path,
        "metadata": metadata or {},
        "embedding": embedding or []
    })
    _save_user_db(user_id, db)

def get_user_files(user_id: str) -> List[Dict[str, Any]]:
    db = _load_user_db(user_id)
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
        for doc in db
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

    db = _load_user_db(user_id)
    results = []

    MIN_BASELINE = 0.48
    MAX_BASELINE = 0.68

    for doc in db:
        doc_emb = doc.get("embedding", [])
        if not doc_emb:
            continue

        raw_sim = cosine_similarity(query_embedding, doc_emb)
        normalized_sim = (raw_sim - MIN_BASELINE) / (MAX_BASELINE - MIN_BASELINE)
        normalized_sim = max(0.0, min(1.0, normalized_sim))
        normalized_sim = math.pow(normalized_sim, 0.75)

        if normalized_sim > 0.10:
            results.append({
                "similarity": round(normalized_sim, 4),
                "filename": doc["filename"],
                "file_path": doc.get("file_path", ""),
                "metadata": doc.get("metadata", {})
            })

    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results[:top_k]

def clear_user_data(user_id: str):
    if kv_db:
        kv_db.delete(f"vector_db:{user_id}")
        return

    with db_lock:
        db = []
        if Config.DB_PATH.exists():
            try:
                with open(Config.DB_PATH, "r", encoding="utf-8") as f:
                    db = json.load(f)
            except Exception:
                pass
        filtered = [doc for doc in db if doc.get("user_id") != user_id]
        if len(filtered) != len(db):
            try:
                with open(Config.DB_PATH, "w", encoding="utf-8") as f:
                    json.dump(filtered, f, indent=2)
            except Exception:
                pass
