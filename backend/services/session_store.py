"""
METLINK USSD Session Store.

In-memory TTL cache for USSD responses to serve Africa's Talking retries
instantly, plus per-session locks to serialise simultaneous requests.

Design:
- Replay cache keyed by (sessionId, text).
- TTL 10 minutes per entry.
- Max 5000 entries; oldest are purged on write if limit is exceeded.
- Lazy purge on every write (no background thread).
- Per-session threading.Lock so simultaneous Africa's Talking requests
  for the same sessionId run sequentially.
- This is a FAST REPLAY PATH ONLY. Never required for correctness.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_SESSION_TTL_SECONDS: float = 600.0   # 10 minutes
_MAX_ENTRIES: int = 5000

# Lock protecting the shared dicts below
_store_lock = threading.Lock()

# {(session_id, text): {"response": str, "ts": float}}
_response_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}

# {session_id: threading.Lock} — per-session locks
_session_locks: Dict[str, threading.Lock] = {}


def _purge_expired_locked() -> None:
    cutoff = time.monotonic() - _SESSION_TTL_SECONDS
    stale = [k for k, entry in _response_cache.items() if entry["ts"] < cutoff]
    for k in stale:
        _response_cache.pop(k, None)

    # Clean unused locks if no cache entries exist for that session
    active_sids = {k[0] for k in _response_cache.keys()}
    dead_locks = [sid for sid in _session_locks if sid not in active_sids]
    for sid in dead_locks:
        _session_locks.pop(sid, None)


def _evict_oldest_locked(count: int) -> None:
    oldest = sorted(_response_cache.items(), key=lambda kv: kv[1]["ts"])[:count]
    for k, _ in oldest:
        _response_cache.pop(k, None)


def cache_response(session_id: str, text: str, response: str) -> None:
    """
    Store the response for (sessionId, text) so identical retries
    are replayed without re-executing logic or database queries.
    Never caches error responses.
    """
    if not response:
        return
    # Never cache service errors or forbidden responses
    if "Service error" in response or "Habaye ikibazo" in response or "Forbidden" in response:
        return

    with _store_lock:
        _purge_expired_locked()
        overflow = len(_response_cache) - _MAX_ENTRIES + 1
        if overflow > 0:
            _evict_oldest_locked(overflow)
        _response_cache[(session_id, text)] = {
            "response": response,
            "ts": time.monotonic(),
        }


def get_cached_response(session_id: str, text: str) -> Optional[str]:
    """
    Return the cached response if within TTL, else None.
    """
    with _store_lock:
        entry = _response_cache.get((session_id, text))
        if entry is None:
            return None
        if time.monotonic() - entry["ts"] > _SESSION_TTL_SECONDS:
            _response_cache.pop((session_id, text), None)
            return None
        return entry["response"]


# Backwards compatibility wrappers
def cache_end_response(session_id: str, text: str) -> None:
    cache_response(session_id, "", text)


def get_cached_end_response(session_id: str) -> Optional[str]:
    return get_cached_response(session_id, "")


def get_session_lock(session_id: str) -> threading.Lock:
    """
    Return (creating if necessary) a per-session Lock.
    """
    with _store_lock:
        if session_id not in _session_locks:
            _session_locks[session_id] = threading.Lock()
        return _session_locks[session_id]


def acquire_session_lock(session_id: str, timeout: float = 5.0) -> bool:
    """
    Acquire the per-session lock with a timeout (default 5.0 seconds).
    """
    lock = get_session_lock(session_id)
    return lock.acquire(timeout=timeout)


def release_session_lock(session_id: str) -> None:
    """
    Release the per-session lock safely.
    """
    lock = get_session_lock(session_id)
    try:
        lock.release()
    except RuntimeError:
        pass


def clear_all() -> None:
    with _store_lock:
        _response_cache.clear()
        _session_locks.clear()
