"""Vercel WSGI entry point. Local development: python app.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from src.app import app  # noqa: E402

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
