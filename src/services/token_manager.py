import json
import time
from config import Config, kv_db
from utils.storage import local_lock, read_json, write_json, update_record


class UserTokenManager:
    def _update(self, device_id, change):
        initial = {"used": 0, "first_used": time.time(), "custom_limit": Config.MAX_USER_TOKENS, "metadata": {}}

        def apply(record):
            if time.time() - record.get("first_used", 0) >= 172800:
                record.update(used=0, first_used=time.time())
            return change(record)

        if kv_db:
            return update_record(f"token_usage:{device_id}", initial, apply)
        with local_lock:
            users = read_json(Config.TOKEN_DB_PATH, {})
            record = users.setdefault(device_id, initial)
            if isinstance(record, int):
                record = users[device_id] = dict(initial, used=record)
            result = apply(record)
            write_json(Config.TOKEN_DB_PATH, users)
            return result

    def register_user(self, device_id, metadata):
        def change(record):
            if not record.get("metadata"):
                record["metadata"] = dict(metadata, first_seen=record["first_used"])
                return True
            return False
        if self._update(device_id, change):
            from utils.webhook import notify_user
            notify_user(device_id, metadata)

    def is_over_limit(self, device_id):
        stats = self.get_usage_stats(device_id)
        return stats["used"] >= stats["limit"]

    def consume(self, device_id, tokens):
        def change(record):
            if record["used"] + tokens > record.get("custom_limit", Config.MAX_USER_TOKENS):
                return False
            record["used"] += tokens
            return True
        return self._update(device_id, change)

    def track_usage(self, device_id, tokens):
        self._update(device_id, lambda record: record.update(used=record["used"] + max(0, tokens)))

    def get_usage_stats(self, device_id):
        return self._update(device_id, lambda record: {
            "used": record["used"], "limit": record.get("custom_limit", Config.MAX_USER_TOKENS),
            "first_used": record["first_used"]})

    def get_all_users(self):
        if kv_db:
            users = {}
            for key in kv_db.scan_iter(match="token_usage:*", count=100):
                raw = kv_db.get(key)
                if raw:
                    users[key.split(":", 1)[1]] = json.loads(raw)
                if len(users) >= 100:
                    break
            return users
        with local_lock:
            return read_json(Config.TOKEN_DB_PATH, {})

    def admin_update_user(self, device_id, new_used, new_limit):
        def change(record):
            if new_used is not None:
                record.update(used=new_used, first_used=time.time())
            if new_limit is not None:
                record["custom_limit"] = new_limit
        self._update(device_id, change)


user_token_manager = UserTokenManager()
