import json
import math
from pathlib import Path
from utils.logger import logger

# Storing vectors securely in local memory file to prevent external DB dependency
VECTOR_DB_PATH = Path("vector_db.json")

def _load_db() -> list:
    if VECTOR_DB_PATH.exists():
        try:
            with open(VECTOR_DB_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load vector DB: {e}")
    return []

def _save_db(db: list):
    try:
        with open(VECTOR_DB_PATH, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save vector DB: {e}")

def add_to_store(filename: str, metadata: dict, embedding: list[float]):
    if not embedding:
        return

    db = _load_db()
    # Replace old entry if a document is re-uploaded
    db = [doc for doc in db if doc.get("filename") != filename]
    db.append({
        "filename": filename,
        "metadata": metadata,
        "embedding": embedding
    })
    
    _save_db(db)
    logger.info(f"[{filename}] Added to Vector Store. Total Docs: {len(db)}")

def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    
    dot = sum(a * b for a, b in zip(v1, v2))
    mag1 = math.sqrt(sum(a * a for a in v1))
    mag2 = math.sqrt(sum(b * b for b in v2))
    
    return dot / (mag1 * mag2) if mag1 and mag2 else 0.0

def search_store(query_embedding: list[float], top_k: int = 5) -> list[dict]:
    if not query_embedding:
        return []
        
    db = _load_db()
    results = []
    
    for doc in db:
        sim = cosine_similarity(query_embedding, doc["embedding"])
        results.append({
            "similarity": sim,
            "filename": doc["filename"],
            "metadata": doc["metadata"]
        })
        
    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results[:top_k]