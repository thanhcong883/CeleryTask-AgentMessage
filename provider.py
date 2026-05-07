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
        """Send a text message or attachments via Telegram Bot API."""
        conf = config.PLATFORMS.get("Telegram", {})
        token = data.get("token", "")
        base_url = f"https://api.telegram.org/bot{token}"

        # Determine appropriate ID field depending on chat type
        chat_id = data.get("group_id") or data.get("user_id")
        content = data.get("content")
        attachments = data.get("attachments")

        # Reply support: if reply_to_message_id is provided, include it in payloads
        reply_to_message_id = data.get("reply_to_message_id")

        try:
            if not attachments:
                url = f"{base_url}/sendMessage"
                payload = {"chat_id": chat_id, "text": content}
                if reply_to_message_id:
                    payload["reply_to_message_id"] = reply_to_message_id
                response = requests.post(url, json=payload, timeout=10)
                response.raise_for_status()
                logger.info("Successfully sent Telegram text message.")
                return response.json()
            else:
                last_response = None
                for i, att in enumerate(attachments):
                    att_type = att.get("type", "document")
                    url_part = ""
                    payload = {"chat_id": chat_id}
                    if i == 0 and content:
                        payload["caption"] = content
                    if i == 0 and reply_to_message_id:
                        payload["reply_to_message_id"] = reply_to_message_id

                    if att_type == "image":
                        url_part = "/sendPhoto"
                        payload["photo"] = att.get("url")
                    elif att_type == "video":
                        url_part = "/sendVideo"
                        payload["video"] = att.get("url")
                    elif att_type == "audio":
                        url_part = "/sendAudio"
                        payload["audio"] = att.get("url")
                    else:
                        url_part = "/sendDocument"
                        payload["document"] = att.get("url")

                    url = f"{base_url}{url_part}"
                    response = requests.post(url, json=payload, timeout=10)
                    response.raise_for_status()
                    last_response = response.json()
                logger.info("Successfully sent Telegram attachment messages.")
                return last_response or {}

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

        # Reply support: build a quote object for zca2api
        reply_to_message_id = data.get("reply_to_message_id")
        if reply_to_message_id:
            payload["quote"] = {"globalMsgId": str(reply_to_message_id)}

        attachments = data.get("attachments")
        if attachments:
            payload["attachments"] = [
                att.get("url") for att in attachments if att.get("url")
            ]

        try:
            response = requests.post(url, json=payload, timeout=30)
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

    # Map attachment type → Baileys message key
    _BAILEYS_KEY = {
        "image": "image",
        "video": "video",
        "audio": "audio",
        "document": "document",
        "file": "document",
        "sticker": "sticker",
    }

    def send(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Send a text or media message via External WhatsApp API (baileys2api).

        baileys2api ``/api/{accountId}/send`` accepts:
        - ``text`` (str): plain text – forwarded as ``{ text }`` to Baileys.
        - ``message`` (object): a raw Baileys message object, e.g.
          ``{ image: { url }, caption }`` – forwarded as-is to
          ``sock.sendMessage(to, message)``.

        When *attachments* are present we build proper Baileys message objects
        so that images / documents / videos / audio are actually delivered.
        """
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

        attachments = data.get("attachments")

        try:
            last_response = None

            if attachments:
                # Send each attachment as a separate Baileys message object.
                for i, att in enumerate(attachments):
                    att_url = att.get("url")
                    if not att_url:
                        continue

                    att_type = (att.get("type") or "document").lower()
                    baileys_key = self._BAILEYS_KEY.get(att_type, "document")

                    # Build the Baileys message object, e.g.:
                    #   { image: { url: "https://..." }, caption: "hello" }
                    baileys_msg: Dict[str, Any] = {
                        baileys_key: {"url": att_url},
                    }

                    # Attach caption only on the first media message
                    if i == 0 and content:
                        baileys_msg["caption"] = content

                    # For documents, include the original filename if available
                    if baileys_key == "document":
                        filename = att.get("name") or att_url.rsplit("/", 1)[-1]
                        baileys_msg["fileName"] = filename
                        mimetype = att.get("mimetype")
                        if mimetype:
                            baileys_msg["mimetype"] = mimetype

                    payload = {
                        "message": baileys_msg,
                        "threadId": conv_id,
                        "type": msg_type,
                    }
                    # Reply support: only attach quotedMessageId on first media
                    reply_to_message_id = data.get("reply_to_message_id")
                    if i == 0 and reply_to_message_id:
                        payload["quotedMessageId"] = str(reply_to_message_id)
                    logger.info(
                        "Sending WhatsApp media (%s) payload: %s", att_type, payload
                    )
                    response = requests.post(url, json=payload, timeout=30)
                    response.raise_for_status()
                    last_response = response.json()

                logger.info(
                    "Successfully sent %d attachment(s) via external WhatsApp API.",
                    len(attachments),
                )
                return last_response or {}
            else:
                # Plain text message
                payload = {
                    "text": content,
                    "threadId": conv_id,
                    "type": msg_type,
                }
                # Reply support
                reply_to_message_id = data.get("reply_to_message_id")
                if reply_to_message_id:
                    payload["quotedMessageId"] = str(reply_to_message_id)
                response = requests.post(url, json=payload, timeout=10)
                response.raise_for_status()
                logger.info("Successfully sent text message via external WhatsApp API.")
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
