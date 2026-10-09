from flask import Flask
from config import Config
from utils.logger import logger
from routes.api import api_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    app.register_blueprint(api_bp)

    logger.info("Application configured and blueprints registered successfully.")
    return app

app = create_app()

if __name__ == "__main__":
    logger.info("Starting up Flask Server...")
    app.run(debug=True, threaded=True)