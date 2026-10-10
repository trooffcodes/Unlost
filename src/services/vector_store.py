import json
import math
import threading
from typing import List, Dict, Any
from config import Config, kv_db
from utils.logger import logger

from utils.storage import local_lock, read_json, write_json, update_record


def _load_user_db(user_id: str) -> List[Dict[str, Any]]:
    if kv_db:
        data = kv_db.get(f"vector_db:{user_id}")
        return json.loads(data) if data else []
    with local_lock:
        return [doc for doc in read_json(Config.DB_PATH, []) if doc.get("user_id") == user_id]


def add_to_store(user_id: str, filename: str, file_path: str, metadata: dict, embedding: List[float]):
    document = {"user_id": user_id, "filename": filename, "file_path": file_path,
                "metadata": metadata or {}, "embedding": embedding}

    def change(db):
        existing = next((i for i, doc in enumerate(db) if doc.get("filename") == filename), None)
        if existing is not None:
            db[existing] = document
        else:
            if len(db) >= Config.MAX_LIBRARY_FILES:
                raise ValueError("Library is full; clear data before uploading more files")
            db.append(document)

    if kv_db:
        update_record(f"vector_db:{user_id}", [], change)
    else:
        with local_lock:
            db = read_json(Config.DB_PATH, [])
            own = [doc for doc in db if doc.get("user_id") == user_id]
            change(own)
            write_json(Config.DB_PATH, [doc for doc in db if doc.get("user_id") != user_id] + own)

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
    else:
        with local_lock:
            db = read_json(Config.DB_PATH, [])
            write_json(Config.DB_PATH, [doc for doc in db if doc.get("user_id") != user_id])
