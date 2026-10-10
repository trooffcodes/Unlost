import json
import time
import threading
from config import Config
from utils.logger import logger

class UserTokenManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.user_usage = self._load_usage()

    def _load_usage(self) -> dict:
        if Config.TOKEN_DB_PATH.exists():
            try:
                with open(Config.TOKEN_DB_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for k, v in data.items():
                        if isinstance(v, int):
                            data[k] = {"used": v, "first_used": time.time(), "custom_limit": Config.MAX_USER_TOKENS}
                    return data
            except Exception as e:
                logger.error(f"Failed to load token usage: {e}")
        return {}

    def _save_usage(self):
        try:
            with open(Config.TOKEN_DB_PATH, "w", encoding="utf-8") as f:
                json.dump(self.user_usage, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to persist token usage: {e}")

    def _check_and_reset(self, device_id: str):
        record = self.user_usage.setdefault(device_id, {
            "used": 0, "first_used": time.time(), "custom_limit": Config.MAX_USER_TOKENS
        })
        # Reset after 48 hours (172,800 seconds)
        if time.time() - record.get("first_used", time.time()) > 172800:
            record["used"] = 0
            record["first_used"] = time.time()
            self._save_usage()

    def is_over_limit(self, device_id: str) -> bool:
        with self.lock:
            self._check_and_reset(device_id)
            rec = self.user_usage[device_id]
            return rec["used"] >= rec.get("custom_limit", Config.MAX_USER_TOKENS)

    def track_usage(self, device_id: str, tokens: int):
        with self.lock:
            self._check_and_reset(device_id)
            rec = self.user_usage[device_id]
            rec["used"] += max(0, tokens)
            self._save_usage()

    def get_usage_stats(self, device_id: str) -> dict:
        with self.lock:
            self._check_and_reset(device_id)
            rec = self.user_usage[device_id]
            return {
                "used": rec["used"],
                "limit": rec.get("custom_limit", Config.MAX_USER_TOKENS),
                "first_used": rec.get("first_used", time.time())
            }

    def get_all_users(self) -> dict:
        with self.lock:
            return dict(self.user_usage)

    def admin_update_user(self, device_id: str, new_used: int | None, new_limit: int | None):
        with self.lock:
            rec = self.user_usage.setdefault(device_id, {"first_used": time.time()})
            if new_used is not None:
                rec["used"] = new_used
            if new_limit is not None:
                rec["custom_limit"] = new_limit
            self._save_usage()

user_token_manager = UserTokenManager()
