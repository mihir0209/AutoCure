"""
Redis Service - Caching, Sessions, and Rate Limiting
Handles Redis operations for real-time data management.
"""

import asyncio
import json
import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from redis.asyncio import Redis

try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from ..config import config

logger = logging.getLogger(__name__)


class RedisService:
    """
    Async Redis service for caching, sessions, pub/sub, and rate limiting.
    """
    
    # Key prefixes for namespace isolation
    PREFIX_SESSION = "session:"
    PREFIX_USER = "user:"
    PREFIX_REPO = "repo:"
    PREFIX_AST = "ast:"
    PREFIX_LOG_BUFFER = "logs:"
    PREFIX_RATE_LIMIT = "ratelimit:"
    PREFIX_LOCK = "lock:"
    PREFIX_PUBSUB = "pubsub:"
    
    def __init__(self):
        self.redis: Optional["Redis"] = None
        self.pubsub = None
        self._initialized = False
        
    async def initialize(self) -> None:
        """Initialize Redis connection."""
        if not REDIS_AVAILABLE:
            logger.error("redis-py not installed. Install with: pip install redis")
            return
            
        if self._initialized:
            return
            
        try:
            self.redis = aioredis.from_url(
                f"redis://{config.redis.host}:{config.redis.port}",
                password=config.redis.password if config.redis.password else None,
                db=config.redis.db,
                encoding="utf-8",
                decode_responses=True,
                max_connections=config.redis.max_connections
            )
            # Test connection
            await self.redis.ping()
            self._initialized = True
            logger.info(f"Redis connected: {config.redis.host}:{config.redis.port}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    async def close(self) -> None:
        """Close Redis connection."""
        if self.redis:
            await self.redis.close()
            self._initialized = False
            logger.info("Redis connection closed")
    
    # =========================================================================
    # WebSocket Session Management
    # =========================================================================
    
    async def register_session(
        self,
        user_id: str,
        connection_id: str,
        repo_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> None:
        """Register a new WebSocket session."""
        session_key = f"{self.PREFIX_SESSION}{connection_id}"
        user_sessions_key = f"{self.PREFIX_USER}{user_id}:sessions"
        
        session_data = {
            "user_id": user_id,
            "connection_id": connection_id,
            "repo_id": repo_id or "",
            "connected_at": asyncio.get_event_loop().time(),
            "last_heartbeat": asyncio.get_event_loop().time(),
            **(metadata or {})
        }
        
        pipe = self.redis.pipeline()
        pipe.hset(session_key, mapping=session_data)
        pipe.expire(session_key, 86400)  # 24 hour TTL
        pipe.sadd(user_sessions_key, connection_id)
        pipe.expire(user_sessions_key, 86400)
        await pipe.execute()
        
        logger.debug(f"Session registered: {connection_id} for user {user_id}")
    
    async def update_session_heartbeat(self, connection_id: str) -> None:
        """Update session heartbeat timestamp."""
        session_key = f"{self.PREFIX_SESSION}{connection_id}"
        await self.redis.hset(
            session_key, 
            "last_heartbeat", 
            asyncio.get_event_loop().time()
        )
    
    async def remove_session(self, user_id: str, connection_id: str) -> None:
        """Remove a WebSocket session."""
        session_key = f"{self.PREFIX_SESSION}{connection_id}"
        user_sessions_key = f"{self.PREFIX_USER}{user_id}:sessions"
        
        pipe = self.redis.pipeline()
        pipe.delete(session_key)
        pipe.srem(user_sessions_key, connection_id)
        await pipe.execute()
        
        logger.debug(f"Session removed: {connection_id}")
    
    async def get_user_sessions(self, user_id: str) -> Set[str]:
        """Get all active session IDs for a user."""
        user_sessions_key = f"{self.PREFIX_USER}{user_id}:sessions"
        return await self.redis.smembers(user_sessions_key)
    
    async def get_session(self, connection_id: str) -> Optional[Dict]:
        """Get session data by connection ID."""
        session_key = f"{self.PREFIX_SESSION}{connection_id}"
        data = await self.redis.hgetall(session_key)
        return data if data else None
    
    # =========================================================================
    # Log Buffer Management
    # =========================================================================
    
    async def buffer_log(
        self,
        user_id: str,
        repo_id: str,
        log_entry: Dict
    ) -> int:
        """Buffer a log entry for processing."""
        buffer_key = f"{self.PREFIX_LOG_BUFFER}{user_id}:{repo_id}"
        
        # Add to list with timestamp for ordering
        log_entry["_buffered_at"] = asyncio.get_event_loop().time()
        
        pipe = self.redis.pipeline()
        pipe.lpush(buffer_key, json.dumps(log_entry))
        pipe.ltrim(buffer_key, 0, 999)  # Keep last 1000 logs
        pipe.expire(buffer_key, 3600)  # 1 hour TTL
        results = await pipe.execute()
        
        return results[0]  # Return current buffer size
    
    async def get_buffered_logs(
        self,
        user_id: str,
        repo_id: str,
        count: int = 100
    ) -> List[Dict]:
        """Get buffered logs for processing."""
        buffer_key = f"{self.PREFIX_LOG_BUFFER}{user_id}:{repo_id}"
        
        # Get logs (LIFO order)
        raw_logs = await self.redis.lrange(buffer_key, 0, count - 1)
        return [json.loads(log) for log in raw_logs]
    
    async def clear_log_buffer(self, user_id: str, repo_id: str) -> None:
        """Clear the log buffer for a repo."""
        buffer_key = f"{self.PREFIX_LOG_BUFFER}{user_id}:{repo_id}"
        await self.redis.delete(buffer_key)
    
    # =========================================================================
    # AST Cache Management
    # =========================================================================
    
    async def cache_ast(
        self,
        repo_id: str,
        file_path: str,
        ast_json: Dict,
        ttl_hours: int = 24
    ) -> None:
        """Cache parsed AST for a file."""
        cache_key = f"{self.PREFIX_AST}{repo_id}:{file_path}"
        
        await self.redis.setex(
            cache_key,
            timedelta(hours=ttl_hours),
            json.dumps(ast_json)
        )
        
        # Track cached files for this repo
        repo_files_key = f"{self.PREFIX_AST}{repo_id}:files"
        await self.redis.sadd(repo_files_key, file_path)
        await self.redis.expire(repo_files_key, ttl_hours * 3600)
    
    async def get_cached_ast(
        self,
        repo_id: str,
        file_path: str
    ) -> Optional[Dict]:
        """Get cached AST for a file."""
        cache_key = f"{self.PREFIX_AST}{repo_id}:{file_path}"
        cached = await self.redis.get(cache_key)
        return json.loads(cached) if cached else None
    
    async def invalidate_ast_cache(
        self,
        repo_id: str,
        file_paths: Optional[List[str]] = None
    ) -> int:
        """Invalidate AST cache for specific files or entire repo."""
        if file_paths:
            # Invalidate specific files
            keys = [f"{self.PREFIX_AST}{repo_id}:{fp}" for fp in file_paths]
            return await self.redis.delete(*keys)
        else:
            # Invalidate all files for repo
            repo_files_key = f"{self.PREFIX_AST}{repo_id}:files"
            file_paths = await self.redis.smembers(repo_files_key)
            
            if file_paths:
                keys = [f"{self.PREFIX_AST}{repo_id}:{fp}" for fp in file_paths]
                keys.append(repo_files_key)
                return await self.redis.delete(*keys)
            return 0
    
    async def get_cached_files_list(self, repo_id: str) -> Set[str]:
        """Get list of files with cached AST for a repo."""
        repo_files_key = f"{self.PREFIX_AST}{repo_id}:files"
        return await self.redis.smembers(repo_files_key)
    
    # =========================================================================
    # Rate Limiting
    # =========================================================================
    
    async def check_rate_limit(
        self,
        user_id: str,
        limit_type: str,
        max_requests: int,
        window_seconds: int = 60
    ) -> tuple[bool, int]:
        """
        Check if user is within rate limit.
        Returns (is_allowed, current_count).
        """
        key = f"{self.PREFIX_RATE_LIMIT}{limit_type}:{user_id}"
        
        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.ttl(key)
        results = await pipe.execute()
        
        current_count = results[0]
        ttl = results[1]
        
        # Set expiry on first request
        if ttl == -1:
            await self.redis.expire(key, window_seconds)
        
        is_allowed = current_count <= max_requests
        
        if not is_allowed:
            logger.warning(
                f"Rate limit exceeded for {user_id}: {limit_type} "
                f"({current_count}/{max_requests})"
            )
        
        return is_allowed, current_count
    
    async def get_rate_limit_remaining(
        self,
        user_id: str,
        limit_type: str,
        max_requests: int
    ) -> int:
        """Get remaining requests for a rate limit."""
        key = f"{self.PREFIX_RATE_LIMIT}{limit_type}:{user_id}"
        current = await self.redis.get(key)
        if current is None:
            return max_requests
        return max(0, max_requests - int(current))
    
    async def reset_rate_limit(self, user_id: str, limit_type: str) -> None:
        """Reset a rate limit for a user."""
        key = f"{self.PREFIX_RATE_LIMIT}{limit_type}:{user_id}"
        await self.redis.delete(key)
    
    # =========================================================================
    # Pub/Sub for Horizontal Scaling
    # =========================================================================
    
    async def publish_log_event(
        self,
        user_id: str,
        event_type: str,
        data: Dict
    ) -> int:
        """Publish a log event for other instances to process."""
        channel = f"{self.PREFIX_PUBSUB}logs:{user_id}"
        message = json.dumps({
            "type": event_type,
            "data": data,
            "timestamp": asyncio.get_event_loop().time()
        })
        return await self.redis.publish(channel, message)
    
    async def subscribe_to_logs(self, user_id: str):
        """Subscribe to log events for a user."""
        if self.pubsub is None:
            self.pubsub = self.redis.pubsub()
        
        channel = f"{self.PREFIX_PUBSUB}logs:{user_id}"
        await self.pubsub.subscribe(channel)
        return self.pubsub
    
    async def unsubscribe_from_logs(self, user_id: str) -> None:
        """Unsubscribe from log events."""
        if self.pubsub:
            channel = f"{self.PREFIX_PUBSUB}logs:{user_id}"
            await self.pubsub.unsubscribe(channel)
    
    # =========================================================================
    # Distributed Locking
    # =========================================================================
    
    async def acquire_lock(
        self,
        lock_name: str,
        timeout_seconds: int = 30
    ) -> bool:
        """Acquire a distributed lock."""
        lock_key = f"{self.PREFIX_LOCK}{lock_name}"
        
        # Use SET NX with expiry for atomic lock acquisition
        acquired = await self.redis.set(
            lock_key,
            "locked",
            nx=True,
            ex=timeout_seconds
        )
        return acquired is not None
    
    async def release_lock(self, lock_name: str) -> None:
        """Release a distributed lock."""
        lock_key = f"{self.PREFIX_LOCK}{lock_name}"
        await self.redis.delete(lock_key)
    
    async def extend_lock(
        self,
        lock_name: str,
        timeout_seconds: int = 30
    ) -> bool:
        """Extend a lock's TTL."""
        lock_key = f"{self.PREFIX_LOCK}{lock_name}"
        return await self.redis.expire(lock_key, timeout_seconds)
    
    # =========================================================================
    # Repository State Tracking
    # =========================================================================
    
    async def set_repo_state(
        self,
        repo_id: str,
        state: str,
        metadata: Optional[Dict] = None
    ) -> None:
        """Set repository sync/processing state."""
        key = f"{self.PREFIX_REPO}{repo_id}:state"
        data = {
            "state": state,
            "updated_at": asyncio.get_event_loop().time(),
            **(metadata or {})
        }
        await self.redis.hset(key, mapping=data)
        await self.redis.expire(key, 3600)  # 1 hour TTL
    
    async def get_repo_state(self, repo_id: str) -> Optional[Dict]:
        """Get repository state."""
        key = f"{self.PREFIX_REPO}{repo_id}:state"
        return await self.redis.hgetall(key)
    
    async def set_repo_commit(self, repo_id: str, commit_hash: str) -> None:
        """Cache the latest commit hash for a repo."""
        key = f"{self.PREFIX_REPO}{repo_id}:commit"
        await self.redis.set(key, commit_hash, ex=86400)  # 24 hour TTL
    
    async def get_repo_commit(self, repo_id: str) -> Optional[str]:
        """Get cached commit hash for a repo."""
        key = f"{self.PREFIX_REPO}{repo_id}:commit"
        return await self.redis.get(key)
    
    # =========================================================================
    # User Data Caching
    # =========================================================================
    
    async def cache_user(self, user_id: str, user_data: Dict, ttl_seconds: int = 300) -> None:
        """Cache user data for quick lookups."""
        key = f"{self.PREFIX_USER}{user_id}:data"
        await self.redis.setex(key, ttl_seconds, json.dumps(user_data))
    
    async def get_cached_user(self, user_id: str) -> Optional[Dict]:
        """Get cached user data."""
        key = f"{self.PREFIX_USER}{user_id}:data"
        cached = await self.redis.get(key)
        return json.loads(cached) if cached else None
    
    async def invalidate_user_cache(self, user_id: str) -> None:
        """Invalidate user cache."""
        key = f"{self.PREFIX_USER}{user_id}:data"
        await self.redis.delete(key)
    
    # =========================================================================
    # Error Tracking
    # =========================================================================
    
    async def track_error(
        self,
        repo_id: str,
        error_hash: str,
        error_data: Dict
    ) -> int:
        """Track an error occurrence and return count."""
        # Use sorted set for error frequency tracking
        errors_key = f"{self.PREFIX_REPO}{repo_id}:errors"
        
        # Increment error count
        count = await self.redis.zincrby(errors_key, 1, error_hash)
        
        # Store error details
        error_detail_key = f"{self.PREFIX_REPO}{repo_id}:error:{error_hash}"
        await self.redis.setex(
            error_detail_key,
            86400,  # 24 hour TTL
            json.dumps(error_data)
        )
        
        return int(count)
    
    async def get_top_errors(
        self,
        repo_id: str,
        count: int = 10
    ) -> List[tuple[str, int]]:
        """Get top N most frequent errors for a repo."""
        errors_key = f"{self.PREFIX_REPO}{repo_id}:errors"
        results = await self.redis.zrevrange(errors_key, 0, count - 1, withscores=True)
        return [(error_hash, int(score)) for error_hash, score in results]
    
    # =========================================================================
    # Health Check
    # =========================================================================
    
    async def health_check(self) -> Dict[str, Any]:
        """Check Redis health and return stats."""
        try:
            info = await self.redis.info()
            return {
                "status": "healthy",
                "connected_clients": info.get("connected_clients"),
                "used_memory_human": info.get("used_memory_human"),
                "uptime_in_seconds": info.get("uptime_in_seconds"),
                "redis_version": info.get("redis_version")
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }


# Global Redis service instance
redis_service = RedisService()
