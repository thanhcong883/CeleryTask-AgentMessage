import logging
import uuid
import json
import requests
from typing import Dict, Any, Optional
from database import redis_client

logger = logging.getLogger(__name__)

def store_received_message(data: Dict[str, Any]):
    """Stores the received message in Redis with a 10-minute expiration."""
    try:
        msg_id = str(uuid.uuid4())
        key = f"received_msg:{msg_id}"
        redis_client.setex(key, 600, json.dumps(data))
        logger.info(f"Stored message {msg_id} in Redis with 10min expiry")
    except Exception as e:
        logger.error(f"Failed to store message in Redis: {e}")

def get_telegram_webhook_info(token: str) -> Dict[str, Any]:
    """Retrieves current webhook configuration from Telegram."""
    url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Failed to get Telegram webhook info: {e}")
        return {"ok": False, "error": str(e)}

def sync_telegram_webhook(bot_id: str, token: str, base_url: str):
    """Sets the Telegram webhook to the current base_url."""
    webhook_url = f"{base_url}/api/hook?platform=telegram&bot_id={bot_id}"

    # Check current webhook first
    info = get_telegram_webhook_info(token)
    if info.get("ok") and info.get("result", {}).get("url") == webhook_url:
        logger.info(f"Telegram webhook for {bot_id} is already correctly set to {webhook_url}")
        return {"ok": True, "message": "Already synced"}

    logger.info(f"Setting Telegram webhook for {bot_id} to {webhook_url}")
    url = f"https://api.telegram.org/bot{token}/setWebhook"
    try:
        response = requests.post(url, json={"url": webhook_url}, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Failed to set Telegram webhook for {bot_id}: {e}")
        raise

def delete_telegram_webhook(token: str):
    """Removes the Telegram webhook."""
    url = f"https://api.telegram.org/bot{token}/deleteWebhook"
    try:
        response = requests.post(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Failed to delete Telegram webhook: {e}")
        return {"ok": False, "error": str(e)}
