import logging
import redis
import os
import config

logger = logging.getLogger(__name__)

# Redis client
try:
    # Use config.REDIS_URL but allow for a simpler connection if that fails
    redis_url = config.REDIS_URL
    redis_client = redis.from_url(redis_url, decode_responses=True)
    redis_client.ping()
except Exception as e:
    logger.error(f"Failed to connect to Redis at {config.REDIS_URL}: {e}")
    # Fallback to localhost if possible, or just re-raise if it's critical
    redis_client = redis.Redis(host="localhost", decode_responses=True)
