"""
Redis Cache Service
Provides caching functionality for API endpoints to improve performance
"""

import redis
import json
import logging
from typing import Any, Optional, Callable
from functools import wraps
import os

logger = logging.getLogger(__name__)

class CacheService:
    """Redis-based caching service with graceful degradation"""
    
    def __init__(self, host='localhost', port=6379, db=0):
        self.enabled = False
        self.redis_client = None
        
        try:
            self.redis_client = redis.Redis(
                host=host,
                port=port,
                db=db,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2
            )
            # Test connection - fail fast if not available
            self.redis_client.ping() 
            self.enabled = True
            logger.info(f"✅ Redis client initialized and verified: {host}:{port}")
        except (redis.ConnectionError, redis.TimeoutError):
            logger.warning(f"⚠️ Redis not available at {host}:{port}. Caching disabled.")
            self.enabled = False
        except Exception as e:
            logger.error(f"❌ Redis initialization error: {e}. Caching disabled.")
            self.enabled = False
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if not self.enabled:
            return None
        
        try:
            value = self.redis_client.get(key)
            if value:
                logger.debug(f"Cache HIT: {key}")
                return json.loads(value)
            logger.debug(f"Cache MISS: {key}")
            return None
        except Exception as e:
            logger.error(f"Cache GET error for {key}: {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: int = 300):
        """Set value in cache with TTL (time-to-live) in seconds"""
        if not self.enabled:
            return False
        
        try:
            serialized = json.dumps(value, default=str)
            self.redis_client.setex(key, ttl, serialized)
            logger.debug(f"Cache SET: {key} (TTL: {ttl}s)")
            return True
        except Exception as e:
            logger.error(f"Cache SET error for {key}: {e}")
            return False
    
    def delete(self, key: str):
        """Delete key from cache"""
        if not self.enabled:
            return False
        
        try:
            self.redis_client.delete(key)
            logger.debug(f"Cache DELETE: {key}")
            return True
        except Exception as e:
            logger.error(f"Cache DELETE error for {key}: {e}")
            return False
    
    def delete_pattern(self, pattern: str):
        """Delete all keys matching pattern (e.g., 'agents:*')"""
        if not self.enabled:
            return False
        
        try:
            keys = self.redis_client.keys(pattern)
            if keys:
                self.redis_client.delete(*keys)
                logger.debug(f"Cache DELETE pattern: {pattern} ({len(keys)} keys)")
            return True
        except Exception as e:
            logger.error(f"Cache DELETE pattern error for {pattern}: {e}")
            return False
    
    def clear_all(self):
        """Clear all cache (use with caution)"""
        if not self.enabled:
            return False
        
        try:
            self.redis_client.flushdb()
            logger.warning("Cache CLEARED: All keys deleted")
            return True
        except Exception as e:
            logger.error(f"Cache CLEAR error: {e}")
            return False
    
    def get_stats(self) -> dict:
        """Get cache statistics"""
        if not self.enabled:
            return {
                "enabled": False,
                "message": "Cache is disabled"
            }
        
        try:
            info = self.redis_client.info('stats')
            return {
                "enabled": True,
                "total_connections": info.get('total_connections_received', 0),
                "total_commands": info.get('total_commands_processed', 0),
                "keyspace_hits": info.get('keyspace_hits', 0),
                "keyspace_misses": info.get('keyspace_misses', 0),
                "hit_rate": self._calculate_hit_rate(
                    info.get('keyspace_hits', 0),
                    info.get('keyspace_misses', 0)
                )
            }
        except Exception as e:
            logger.error(f"Cache STATS error: {e}")
            return {"enabled": True, "error": str(e)}
    
    def _calculate_hit_rate(self, hits: int, misses: int) -> str:
        """Calculate cache hit rate percentage"""
        total = hits + misses
        if total == 0:
            return "0%"
        return f"{(hits / total * 100):.2f}%"


# Global cache instance
cache = CacheService(
    host=os.getenv('REDIS_HOST', 'localhost'),
    port=int(os.getenv('REDIS_PORT', 6379)),
    db=int(os.getenv('REDIS_DB', 0))
)


def cached(ttl: int = 300, key_prefix: str = ""):
    """
    Decorator for caching endpoint responses
    
    Usage:
        @cached(ttl=60, key_prefix="agents")
        def get_agents():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Build cache key from function name and arguments
            cache_key = f"{key_prefix}:{func.__name__}"
            
            # Add URL params to cache key if present
            if kwargs:
                # Sort kwargs for consistent keys
                sorted_kwargs = sorted(kwargs.items())
                params_str = ":".join([f"{k}={v}" for k, v in sorted_kwargs if k not in ['request', 'db']])
                if params_str:
                    cache_key += f":{params_str}"
            
            # Try to get from cache
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # Execute function
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
            
            # Store in cache
            cache.set(cache_key, result, ttl)
            
            return result
        
        return wrapper
    return decorator


def invalidate_cache(pattern: str):
    """
    Helper function to invalidate cache by pattern
    
    Usage:
        invalidate_cache("agents:*")  # Clear all agent caches
    """
    cache.delete_pattern(pattern)


# Import asyncio for coroutine check
import asyncio
