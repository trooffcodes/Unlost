import os
import sys
from pathlib import Path
import pytest
import fakeredis

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
os.environ['SECRET_KEY'] = 'test-only-session-key-32-characters-long'
os.environ.pop('VERCEL', None)
os.environ.pop('VERCEL_ENV', None)
os.environ.pop('REDIS_URL', None)
os.environ.pop('KV_URL', None)
from app import create_app
from config import Config


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    import config
    from routes import api
    from services import pipeline, token_manager, vector_store
    from utils import storage, telemetry, operations
    for module in [config, api, pipeline, token_manager, vector_store, storage, telemetry, operations]:
        monkeypatch.setattr(module, 'kv_db', None)
    for name in ['DB_PATH', 'TOKEN_DB_PATH', 'TELEMETRY_DB_PATH', 'FEEDBACK_DB_PATH']:
        monkeypatch.setattr(Config, name, tmp_path / f'{name}.json')
    monkeypatch.setattr(Config, 'USER_DATA_DIR', tmp_path / 'devices')
    monkeypatch.setattr(Config, 'ADMIN_PASSWORD', None)
    monkeypatch.setattr(Config, 'GEMINI_API_KEY', 'synthetic-test-key')
    for name in ['WEBHOOK_USER', 'WEBHOOK_FILE', 'WEBHOOK_ERROR', 'WEBHOOK_FEEDBACK']:
        monkeypatch.setattr(Config, name, None)
    pipeline.jobs_tracker.clear()


@pytest.fixture
def redis_db(monkeypatch):
    import config
    from routes import api
    from services import pipeline, token_manager, vector_store
    from utils import storage, telemetry
    db = fakeredis.FakeRedis(decode_responses=True)
    for module in [config, api, pipeline, token_manager, vector_store, storage, telemetry]:
        monkeypatch.setattr(module, 'kv_db', db)
    return db


@pytest.fixture
def client():
    application = create_app()
    application.config.update(TESTING=True)
    return application.test_client()
