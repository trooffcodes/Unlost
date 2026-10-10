from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException
from redis.exceptions import RedisError
from config import Config
from utils.logger import logger
from routes.api import api_bp

def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(Config)
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      SESSION_COOKIE_SECURE=Config.IS_VERCEL, PERMANENT_SESSION_LIFETIME=31536000,
                      MAX_FORM_MEMORY_SIZE=100_000, MAX_FORM_PARTS=110)
    app.register_blueprint(api_bp)

    @app.before_request
    def protect_mutations():
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if request.headers.get("X-Unlost-Request") != "1":
                return jsonify(success=False, error="Missing request protection header"), 403

    @app.after_request
    def response_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        if not request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(success=False, error=error.description), error.code

    @app.errorhandler(RedisError)
    def storage_error(error):
        logger.error("Persistent storage unavailable (%s)", type(error).__name__)
        return jsonify(success=False, error="Storage temporarily unavailable; please retry"), 503

    @app.errorhandler(Exception)
    def unexpected_error(error):
        logger.error("Request failed (%s)", type(error).__name__)
        return jsonify(success=False, error="Request failed; please retry"), 500
    logger.info("Unlost successfully initialized.")
    return app

app = create_app()

if __name__ == "__main__":
    logger.info("Starting local server on http://localhost:5000")
    app.run(debug=False, threaded=True)
