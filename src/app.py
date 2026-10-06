from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from services.validation import (
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE,
    check_duplicate,
    check_file_corruption,
    check_file_presence,
    check_file_size,
    check_file_type,
)

app = Flask(__name__)

UPLOAD_FOLDER = Path("uploads")
UPLOAD_FOLDER.mkdir(exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")

    # Step-by-step execution control in app.py
    validators = [
        lambda: check_file_presence(file),
        lambda: check_file_size(file),
        lambda: check_file_type(file),
        lambda: check_file_corruption(file),
        lambda: check_duplicate(file, UPLOAD_FOLDER)
    ]

    for validator in validators:
        is_valid, error_message = validator()
        if not is_valid:
            return error_message, 400

    # Safe Saving & Handling Collisions
    original_filename = file.filename or ""
    suffix = Path(original_filename).suffix.lower()
    filename = secure_filename(original_filename)
    destination = UPLOAD_FOLDER / filename
    
    if destination.exists():
        stem = destination.stem
        counter = 1
        while destination.exists():
            filename = f"{stem}_{counter}{suffix}"
            destination = UPLOAD_FOLDER / filename
            counter += 1

    file.save(destination)
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True)