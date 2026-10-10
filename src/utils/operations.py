from contextlib import contextmanager
import threading
from werkzeug.exceptions import Conflict
from config import kv_db

# Fixed local stripes keep development locks bounded.
_locks = [threading.Lock() for _ in range(64)]


@contextmanager
def device_operation(device_id):
    lock = kv_db.lock(f"operation:{device_id}", timeout=300, blocking_timeout=0) if kv_db else _locks[hash(device_id) % len(_locks)]
    if not lock.acquire(blocking=False):
        raise Conflict("Another document operation is running; please retry")
    try:
        yield
    finally:
        lock.release()
