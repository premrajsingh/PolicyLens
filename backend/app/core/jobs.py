"""Single-process coordination. Deploy one worker with this SQLite edition."""

from contextlib import contextmanager
from threading import Lock

from app.core.errors import AppError

_registry_lock = Lock()
_locks: dict[str, Lock] = {}


@contextmanager
def document_lock(document_id: str):
    with _registry_lock:
        lock = _locks.setdefault(document_id, Lock())
    if not lock.acquire(blocking=False):
        raise AppError(
            "This document is already processing. Please wait.",
            status_code=409,
            code="document_busy",
        )
    try:
        yield
    finally:
        lock.release()
