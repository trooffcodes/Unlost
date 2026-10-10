from flask import Flask
from config import Config
from utils.logger import logger
from routes.api import api_bp

def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(Config)
    app.register_blueprint(api_bp)
    logger.info("Unlost successfully initialized.")
    return app

app = create_app()

if __name__ == "__main__":
    logger.info("Starting local server on http://localhost:5000")
    app.run(debug=True, threaded=True)
