from flask import Blueprint, jsonify, request, render_template
from werkzeug.utils import secure_filename

from config import Config
from utils.logger import logger, time_it
from utils.media import compress_for_ocr, compress_for_llm
from utils.validation import validate_upload
from services.ocr import extract_document_text
from services.ai import extract_semantic_metadata, generate_embedding
from services.vector_store import add_to_store, search_store

api_bp = Blueprint("api", __name__)

@api_bp.route("/")
def index():
    return render_template("index.html")

@api_bp.route("/upload", methods=["POST"])
@time_it
def upload():
    logger.info("--- New Upload Request Started ---")
    file = request.files.get("file")
    if not file:
        return jsonify({"success": False, "error": "No file uploaded"}), 400

    file_bytes = file.read()
    filename = secure_filename(file.filename or "upload")

    error = validate_upload(file_bytes, filename, Config.UPLOAD_FOLDER)
    if error:
        return jsonify({"success": False, "error": error}), 400

    dest = Config.UPLOAD_FOLDER / filename
    stem, suffix = dest.stem, dest.suffix
    counter = 1
    while dest.exists():
        dest = Config.UPLOAD_FOLDER / f"{stem}_{counter}{suffix}"
        counter += 1
        
    with open(dest, "wb") as f:
        f.write(file_bytes)

    try:
        ocr_ready_bytes = compress_for_ocr(file_bytes, suffix)
        llm_ready_bytes = compress_for_llm(file_bytes, suffix)

        extracted_text = extract_document_text(ocr_ready_bytes, filename)
        
        document_metadata = extract_semantic_metadata(
            file_bytes=llm_ready_bytes, 
            filename=filename, 
            ocr_text=extracted_text
        )

        # Vector Embeddings Check
        semantic_text = document_metadata.get("semantic_search_text", "")
        if semantic_text:
            logger.info(f"[{filename}] Generating vector embeddings...")
            embedding = generate_embedding(semantic_text)
            if embedding:
                add_to_store(filename, document_metadata, embedding)

        logger.info(f"[{filename}] Pipeline processing completed successfully.")
        return jsonify({"success": True, "filename": dest.name, "metadata": document_metadata})
        
    except Exception as exc:
        logger.error(f"[{filename}] Fatal Error during processing: {str(exc)}", exc_info=True)
        return jsonify({"success": False, "error": "Internal processing error. Check logs."}), 500

@api_bp.route("/search", methods=["POST"])
@time_it
def search_documents():
    data = request.get_json() or {}
    query = data.get("query")
    
    if not query:
        return jsonify({"success": False, "error": "Query string is required"}), 400
        
    try:
        logger.info(f"Performing Semantic Search for: '{query}'")
        query_embedding = generate_embedding(query)
        
        if not query_embedding:
            return jsonify({"success": False, "error": "Failed to generate query embeddings"}), 500

        results = search_store(query_embedding)
        return jsonify({"success": True, "results": results})
        
    except Exception as exc:
        logger.error(f"Search API Error: {str(exc)}", exc_info=True)
        return jsonify({"success": False, "error": "Search engine error. Check logs."}), 500