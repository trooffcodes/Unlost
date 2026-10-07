from pathlib import Path
from flask import Flask, jsonify, render_template, request
from werkzeug.utils import secure_filename

from utils.logger import logger, time_it
from utils.media import compress_file
from services.ocr import extract_document_text
from services.validation import validate_upload

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = Path("uploads")
app.config["UPLOAD_FOLDER"].mkdir(exist_ok=True)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
@time_it
def upload():
    file = request.files.get("file")
    if not file:
        return jsonify({"success": False, "error": "No file uploaded"}), 400

    file_bytes = file.read()
    filename = secure_filename(file.filename or "upload")

    error = validate_upload(file_bytes, filename, app.config["UPLOAD_FOLDER"])
    if error:
        logger.warning(f"Validation failed for {filename}: {error}")
        return jsonify({"success": False, "error": error}), 400

    dest = app.config["UPLOAD_FOLDER"] / filename
    stem, suffix = dest.stem, dest.suffix
    counter = 1
    
    while dest.exists():
        dest = app.config["UPLOAD_FOLDER"] / f"{stem}_{counter}{suffix}"
        counter += 1

    with open(dest, "wb") as f:
        f.write(file_bytes)
    logger.info(f"File saved to {dest}")

    try:
        compressed_bytes = compress_file(file_bytes, suffix)
        logger.info(f"Size after compression: {len(compressed_bytes) / 1024:.1f} KB")
        with open("commpressed.jpg", "wb") as f:
            f.write(compressed_bytes)
        logger.info(f"Compressed file saved")
        

        extracted_text = extract_document_text(compressed_bytes, filename)
        logger.info(f"Extraction successful for {filename}")

        return jsonify({
            "success": True,
            "filename": dest.name,
            "text": extracted_text
        })
    except Exception as exc:
        logger.error(f"Error processing {filename}: {str(exc)}")
        return jsonify({"success": False, "error": str(exc)}), 500


if __name__ == "__main__":
    logger.info("Starting application...")
    app.run(debug=True)