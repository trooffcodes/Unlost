"""Atomic JSON updates for Redis; local files are for single-process development."""
import json
import os
import threading
from copy import deepcopy
from redis.exceptions import WatchError
from config import kv_db

local_lock = threading.RLock()


def read_json(path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return deepcopy(default)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value), encoding="utf-8")
    os.replace(temporary, path)


def update_record(key, default, change, ttl=None):
    # WATCH protects against other workers, instances, and concurrent requests.
    for _ in range(20):
        with kv_db.pipeline() as pipe:
            try:
                pipe.watch(key)
                raw = pipe.get(key)
                record = json.loads(raw) if raw else deepcopy(default)
                result = change(record)
                pipe.multi()
                pipe.set(key, json.dumps(record), ex=ttl)
                pipe.execute()
                return result
            except WatchError:
                continue
    raise RuntimeError("Storage contention; please retry")
