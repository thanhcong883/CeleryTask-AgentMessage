"""Provider interfaces for connecting to different messaging platforms."""

import logging
import requests
from requests.exceptions import RequestException
from typing import Dict, Any

import config

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
        url = conf.get("url", "").format(token=data.get("token", ""))

        # Determine appropriate ID field depending on chat type
        chat_type = data.get("type", "")
        chat_id = (
            data.get("group_id")
            if chat_type in ["group", "supergroup"]
            else data.get("user_id")
        )

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
    """Provider for sending messages to Zalo Official Account."""

    def send(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Send a text message via Zalo Open API."""
        logger.info("Sending Zalo message with data: %s", _mask_token(data))
        conf = config.PLATFORMS.get("Zalo", {})

        chat_type = data.get("type", "").strip()
        is_private = chat_type == "private"
        url = conf.get("private_url") if is_private else conf.get("group_url")

        headers = {"access_token": data.get("token", "")}
        recipient_id = data.get("user_id") if is_private else data.get("group_id")

        payload = {
            "recipient": {"user_id" if is_private else "group_id": recipient_id},
            "message": {"text": data.get("content")},
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            logger.info("Successfully sent Zalo message.")
            return response.json()
        except RequestException as e:
            logger.error(
                "Failed to send Zalo message. Data: %s, Error: %s",
                _mask_token(data),
                str(e),
            )
            raise


# Global dictionary holding provider instances
PROVIDERS: Dict[str, Any] = {
    "Telegram": TelegramProvider(),
    "Zalo": ZaloProvider(),
}
