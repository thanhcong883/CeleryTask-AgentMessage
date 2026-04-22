import hashlib
import logging
import requests
from requests.exceptions import RequestException
from typing import Dict, Any

import config
from database import redis_client

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def _mask_token(data: Dict[str, Any]) -> Dict[str, Any]:
    """Helper function to hide sensitive tokens from logged data."""
    if not isinstance(data, dict):
        return data
    safe_data = data.copy()
    if "token" in safe_data:
        safe_data["token"] = "***"
    return safe_data


class TelegramProvider:
    """Provider for sending messages to Telegram."""

    def send(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Send a text message via Telegram Bot API."""
        conf = config.PLATFORMS.get("Telegram", {})
        # todo: get token from redis by bot_id
        url = conf.get("url", "").format(token=data.get("token", ""))

        # Determine appropriate ID field depending on chat type
        chat_id = data.get("group_id") or data.get("user_id")

        payload = {
            "chat_id": chat_id,
            "text": data.get("content"),
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info("Successfully sent Telegram message.")
            return response.json()
        except RequestException as e:
            logger.error(
                "Failed to send Telegram message. Data: %s, Error: %s",
                _mask_token(data),
                str(e),
            )
            raise


class ZaloProvider:
    """Provider for sending messages to Zalo via External API."""

    def send(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Send a text message via External Zalo API."""
        logger.info(
            "Sending Zalo message through external API with data: %s", _mask_token(data)
        )

        # Bot ID is required to identify the account in the external system.
        bot_id = data.get("bot_id")
        if not bot_id:
            logger.error("No bot_id provided for message send.")
            raise ValueError("bot_id is required for messages")

        url = f"{config.ZALO_EXTERNAL_API_BASE}/api/{bot_id}/send"

        # Map types: 'private' -> 'user'
        msg_type = data.get("type", "user")
        if msg_type == "private":
            msg_type = "user"

        # Mark before sending to prevent race condition (webhook arrives before API response)
        content = data.get("content", "")
        # Get conv_id from send data (same as platform_conv_id in webhook)
        conv_id = data.get("group_id") or data.get("user_id")
        content_hash = hashlib.md5((content or "").encode()).hexdigest()
        redis_client.setex(f"bot_sent:{conv_id}:{content_hash}", 60, "1")

        payload = {
            "text": content,
            "threadId": conv_id,
            "type": msg_type,
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info("Successfully sent message via external API.")
            return response.json()
        except RequestException as e:
            logger.error(
                "Failed to send message via external API. URL: %s, Error: %s",
                url,
                str(e),
            )
            raise


class WhatsappProvider:
    """Provider for sending messages to WhatsApp via External API."""

    def send(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Send a text message via External WhatsApp API."""
        logger.info(
            "Sending WhatsApp message through external API with data: %s",
            _mask_token(data),
        )

        # Bot ID is required to identify the account in the external system.
        bot_id = data.get("bot_id")
        if not bot_id:
            logger.error("No bot_id provided for message send.")
            raise ValueError("bot_id is required for messages")

        url = f"{config.WHATSAPP_EXTERNAL_API_BASE}/api/{bot_id}/send"

        # Map types: 'private' -> 'user'
        msg_type = data.get("type", "user")
        if msg_type == "private":
            msg_type = "user"

        # Mark before sending to prevent race condition (webhook arrives before API response)
        content = data.get("content", "")
        # Get conv_id from send data (same as platform_conv_id in webhook)
        conv_id = data.get("group_id") or data.get("user_id")
        content_hash = hashlib.md5((content or "").encode()).hexdigest()
        redis_client.setex(f"bot_sent:{conv_id}:{content_hash}", 60, "1")

        payload = {
            "text": content,
            "threadId": conv_id,
            "type": msg_type,
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info("Successfully sent message via external WhatsApp API.")
            return response.json()
        except RequestException as e:
            logger.error(
                "Failed to send message via external WhatsApp API. URL: %s, Error: %s",
                url,
                str(e),
            )
            raise


PROVIDERS: Dict[str, Any] = {
    "Telegram": TelegramProvider(),
    "Whatsapp": WhatsappProvider(),
    "Zalo": ZaloProvider(),
}
