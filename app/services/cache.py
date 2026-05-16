"""Optional Redis cache for RAG queries and small API hot paths."""

from __future__ import annotations

import json
from typing import Any

from app.core.config import get_settings

_client: Any | None = None
_connect_failed = False


def _client_get():
    global _client, _connect_failed
    if _client is not None:
        return _client
    if _connect_failed:
        return None
    settings = get_settings()
    if not settings.redis_url:
        return None
    try:
        import redis  # type: ignore

        r = redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=1.5)
        r.ping()
        _client = r
        return _client
    except Exception:
        _connect_failed = True
        return None


def cache_get_json(key: str) -> Any | None:
    r = _client_get()
    if not r:
        return None
    try:
        raw = r.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def cache_set_json(key: str, value: Any, ttl_seconds: int) -> None:
    r = _client_get()
    if not r:
        return
    try:
        r.setex(key, ttl_seconds, json.dumps(value))
    except Exception:
        pass


def redis_ready() -> bool:
    return _client_get() is not None
