import json
import time
import threading
from config import Config, kv_db
from utils.logger import logger

class UserTokenManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.user_usage = self._load_local_usage()

    def _load_local_usage(self) -> dict:
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

    def _save_local_usage(self):
        try:
            with open(Config.TOKEN_DB_PATH, "w", encoding="utf-8") as f:
                json.dump(self.user_usage, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to persist token usage: {e}")

    def _get_record(self, device_id: str) -> dict:
        if kv_db:
            val = kv_db.get(f"token_usage:{device_id}")
            if val:
                return json.loads(val)
            return {"used": 0, "first_used": time.time(), "custom_limit": Config.MAX_USER_TOKENS}
        else:
            return self.user_usage.setdefault(device_id, {
                "used": 0, "first_used": time.time(), "custom_limit": Config.MAX_USER_TOKENS
            })

    def _save_record(self, device_id: str, record: dict):
        if kv_db:
            kv_db.set(f"token_usage:{device_id}", json.dumps(record))
        else:
            self.user_usage[device_id] = record
            self._save_local_usage()

    def _check_and_reset(self, device_id: str) -> dict:
        record = self._get_record(device_id)
        if time.time() - record.get("first_used", time.time()) > 172800:
            record["used"] = 0
            record["first_used"] = time.time()
            self._save_record(device_id, record)
        return record

    def is_over_limit(self, device_id: str) -> bool:
        with self.lock:
            rec = self._check_and_reset(device_id)
            return rec["used"] >= rec.get("custom_limit", Config.MAX_USER_TOKENS)

    def track_usage(self, device_id: str, tokens: int):
        with self.lock:
            rec = self._check_and_reset(device_id)
            rec["used"] += max(0, tokens)
            self._save_record(device_id, rec)

    def get_usage_stats(self, device_id: str) -> dict:
        with self.lock:
            rec = self._check_and_reset(device_id)
            return {
                "used": rec["used"],
                "limit": rec.get("custom_limit", Config.MAX_USER_TOKENS),
                "first_used": rec.get("first_used", time.time())
            }

    def get_all_users(self) -> dict:
        if kv_db:
            users = {}
            for key in kv_db.scan_iter(match="token_usage:*"):
                dev_id = key.split(":", 1)[1]
                users[dev_id] = json.loads(kv_db.get(key))
            return users
        with self.lock:
            return dict(self.user_usage)

    def admin_update_user(self, device_id: str, new_used: int | None, new_limit: int | None):
        with self.lock:
            rec = self._get_record(device_id)
            if new_used is not None:
                rec["used"] = new_used
            if new_limit is not None:
                rec["custom_limit"] = new_limit
            self._save_record(device_id, rec)

user_token_manager = UserTokenManager()
