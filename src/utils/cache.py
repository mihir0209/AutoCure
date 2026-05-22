"""
Safe async cache wrapper around RedisService.
Every method returns None/False on failure so callers never handle Redis errors.
"""

import json
import logging
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)


def _redis():
    from database.redis_service import redis_service
    return redis_service


def _available() -> bool:
    rs = _redis()
    return rs is not None and rs.redis is not None and rs._initialized


async def get_cached(key: str) -> Optional[Any]:
    """Get a cached value. Returns None on miss or Redis failure."""
    if not _available():
        return None
    try:
        raw = await _redis().redis.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        logger.debug("Cache GET %s failed: %s", key, e)
        return None


async def set_cached(key: str, data: Any, ttl: int = 3600) -> bool:
    """Set a cached value with TTL in seconds. Returns False on failure."""
    if not _available():
        return False
    try:
        await _redis().redis.setex(key, ttl, json.dumps(data, default=str))
        return True
    except Exception as e:
        logger.debug("Cache SET %s failed: %s", key, e)
        return False


async def delete_cached(*keys: str) -> bool:
    """Delete one or more cache keys. Returns False on failure."""
    if not _available() or not keys:
        return False
    try:
        await _redis().redis.delete(*keys)
        return True
    except Exception as e:
        logger.debug("Cache DEL %s failed: %s", keys, e)
        return False


async def check_rate(user_id: str, limit_type: str, max_req: int, window: int = 60) -> Tuple[bool, int]:
    """Check rate limit. Returns (is_allowed, current_count). Always allows on Redis failure."""
    if not _available():
        return True, 0
    try:
        return await _redis().check_rate_limit(user_id, limit_type, max_req, window)
    except Exception as e:
        logger.debug("Rate check failed: %s", e)
        return True, 0


async def buffer_log(user_id: str, log_entry: dict) -> int:
    """Buffer a log entry to Redis. Returns 0 on failure."""
    if not _available():
        return 0
    try:
        return await _redis().buffer_log(user_id, "", log_entry)
    except Exception as e:
        logger.debug("Log buffer failed: %s", e)
        return 0


async def clear_log_buffer(user_id: str) -> None:
    """Clear Redis log buffer for a user."""
    if not _available():
        return
    try:
        await _redis().clear_log_buffer(user_id, "")
    except Exception:
        pass
