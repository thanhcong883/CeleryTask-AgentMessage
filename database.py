import logging
import redis
import os
import config

logger = logging.getLogger(__name__)

CONFIG_REDIS_KEY = "LATEST_CONFIG_KEY"

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

def get_system_config():
    """Retrieves the system configuration from Redis, falling back to config.py."""
    try:
        stored_config = redis_client.hgetall(CONFIG_REDIS_KEY)
        if not stored_config:
            # Fallback to config.py values
            return {
                "BASE_URL": config.BASE_URL
            }
        return stored_config
    except Exception as e:
        logger.error(f"Error fetching system config from Redis: {e}")
        return {"BASE_URL": config.BASE_URL}

def update_system_config(new_config: dict):
    """Updates the system configuration in Redis."""
    try:
        if new_config:
            # Use hset with mapping to update multiple fields at once
            redis_client.hset(CONFIG_REDIS_KEY, mapping=new_config)
            return True
    except Exception as e:
        logger.error(f"Error updating system config in Redis: {e}")
    return False
