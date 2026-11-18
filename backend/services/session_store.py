"""
METLINK USSD Session Store.

In-memory TTL cache for final END responses to serve Africa's Talking retries
instantly, plus per-session locks to serialise simultaneous confirm requests.

Design:
- TTL 10 minutes per session entry.
- Max 5000 entries; oldest are purged on write if limit is exceeded.
- Lazy purge on every write (no background thread).
- Per-session threading.Lock so two simultaneous Africa's Talking retries
  for the same sessionId run one after the other, not in parallel.

This is a FAST REPLAY PATH ONLY. It is never required for correctness; the
database (find_recent_duplicate) is the source of truth for idempotency.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_SESSION_TTL_SECONDS: float = 600.0   # 10 minutes
_MAX_ENTRIES: int = 5000

# Lock protecting the two shared dicts below.
_store_lock = threading.Lock()

# {session_id: {"text": str, "ts": float}}
_end_cache: Dict[str, Dict[str, Any]] = {}

# {session_id: threading.Lock}  — per-session submit locks
_session_locks: Dict[str, threading.Lock] = {}


def _purge_expired_locked() -> None:
    """
    Remove entries older than TTL. Caller must hold _store_lock.
    """
    cutoff = time.monotonic() - _SESSION_TTL_SECONDS
    stale = [sid for sid, entry in _end_cache.items() if entry["ts"] < cutoff]
    for sid in stale:
        _end_cache.pop(sid, None)
        _session_locks.pop(sid, None)


def _evict_oldest_locked(count: int) -> None:
    """
    Remove the oldest `count` entries. Caller must hold _store_lock.
    """
    oldest = sorted(_end_cache.items(), key=lambda kv: kv[1]["ts"])[:count]
    for sid, _ in oldest:
        _end_cache.pop(sid, None)
        _session_locks.pop(sid, None)


def cache_end_response(session_id: str, text: str) -> None:
    """
    Store the final END text for a session so identical retries are replayed
    without hitting the database again.
    """
    with _store_lock:
        _purge_expired_locked()
        overflow = len(_end_cache) - _MAX_ENTRIES + 1
        if overflow > 0:
            _evict_oldest_locked(overflow)
        _end_cache[session_id] = {"text": text, "ts": time.monotonic()}


def get_cached_end_response(session_id: str) -> Optional[str]:
    """
    Return the cached END text if still within TTL, else None.
    """
    with _store_lock:
        entry = _end_cache.get(session_id)
        if entry is None:
            return None
        if time.monotonic() - entry["ts"] > _SESSION_TTL_SECONDS:
            _end_cache.pop(session_id, None)
            _session_locks.pop(session_id, None)
            return None
        return entry["text"]


def get_session_lock(session_id: str) -> threading.Lock:
    """
    Return (creating if necessary) a per-session Lock so concurrent confirm
    requests for the same sessionId are serialised.
    """
    with _store_lock:
        if session_id not in _session_locks:
            _session_locks[session_id] = threading.Lock()
        return _session_locks[session_id]


def clear_all() -> None:
    """Clear all session state. Used in tests only."""
    with _store_lock:
        _end_cache.clear()
        _session_locks.clear()
