import hashlib
import logging
import os
import tempfile
import requests
from requests.exceptions import RequestException
from typing import Dict, Any, Optional
from urllib.parse import urlparse

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


def _download_to_temp(url: str) -> Optional[str]:
    """Download a file from URL to a temporary file, return its path or None."""
    try:
        parsed = urlparse(url)
        filename = os.path.basename(parsed.path) or "document"
        suffix = ""
        if "." in filename:
            suffix = "." + filename.rsplit(".", 1)[-1]
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix="tg_")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        resp = requests.get(url, stream=True, timeout=30, headers=headers)
        resp.raise_for_status()
        for chunk in resp.iter_content(chunk_size=8192):
            tmp.write(chunk)
        tmp.close()
        file_size = os.path.getsize(tmp.name)
        if file_size == 0:
            logger.error("Downloaded file is 0 bytes from %s", url)
            os.remove(tmp.name)
            return None
        logger.info("Downloaded %d bytes from %s to %s", file_size, url, tmp.name)
        return tmp.name
    except Exception as e:
        logger.error("Failed to download %s for Telegram upload: %s", url, e)
        return None


def _extract_filename_from_url(url: str) -> str:
    """Extract a human-readable filename from a URL."""
    parsed = urlparse(url)
    basename = os.path.basename(parsed.path) or "document"
    return basename


def _build_telegram_mention_text(content: str, mentions: list) -> str:
    """Convert mentions into HTML-formatted text with tg://user links.

    Processes mentions from right to left to preserve character offsets.
    """
    if not mentions or not content:
        return content

    # Sort by offset descending so earlier offsets are not shifted
    sorted_mentions = sorted(mentions, key=lambda m: m["offset"], reverse=True)
    result = content
    for m in sorted_mentions:
        offset = m["offset"]
        length = m["length"]
        user_id = m["user_id"]
        display = result[offset : offset + length]
        link = f'<a href="tg://user?id={user_id}">{display}</a>'
        result = result[:offset] + link + result[offset + length :]
    return result


def _build_whatsapp_mentions(mentions: list) -> list:
    """Convert generic mention items to Baileys JID format."""
    if not mentions:
        return []
    jids = []
    for m in mentions:
        uid = m["user_id"]
        if "@" not in uid:
            uid = f"{uid}@s.whatsapp.net"
        jids.append(uid)
    return jids


def _build_zalo_mentions(mentions: list) -> list:
    """Convert generic mention items to zca-js Mention format {pos, uid, len}."""
    if not mentions:
        return []
    return [{"pos": m["offset"], "uid": m["user_id"], "len": m["length"]} for m in mentions]


class TelegramProvider:
    """Provider for sending messages to Telegram."""

    # Types that can be sent reliably via URL in JSON payload
    _URL_TYPES = {"image"}

    def send(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Send a text message or attachments via Telegram Bot API."""
        conf = config.PLATFORMS.get("Telegram", {})
        token = data.get("token", "")
        base_url = f"https://api.telegram.org/bot{token}"

        # Determine appropriate ID field depending on chat type
        chat_id = data.get("group_id") or data.get("user_id")
        content = data.get("content")
        attachments = data.get("attachments")

        # Reply support: if reply_to is provided, include it in payloads
        reply_to = data.get("reply_to")
        mentions = data.get("mentions")

        try:
            if not attachments:
                url = f"{base_url}/sendMessage"
                # If mentions exist, use HTML parse_mode with tg://user links
                if mentions:
                    formatted_text = _build_telegram_mention_text(content, mentions)
                    payload = {"chat_id": chat_id, "text": formatted_text, "parse_mode": "HTML"}
                else:
                    payload = {"chat_id": chat_id, "text": content}
                if reply_to:
                    payload["reply_to_message_id"] = reply_to
                response = requests.post(url, json=payload, timeout=10)
                response.raise_for_status()
                logger.info("Successfully sent Telegram text message.")
                return response.json()
            else:
                last_response = None
                for i, att in enumerate(attachments):
                    att_type = att.get("type", "document")
                    att_url = att.get("url")

                    form_data = {"chat_id": chat_id}
                    if i == 0 and content:
                        if mentions:
                            form_data["caption"] = _build_telegram_mention_text(content, mentions)
                            form_data["parse_mode"] = "HTML"
                        else:
                            form_data["caption"] = content
                    if i == 0 and reply_to:
                        form_data["reply_to_message_id"] = reply_to

                    if att_type == "image":
                        # Images work fine with URL in JSON payload
                        url_part = "/sendPhoto"
                        payload = {**form_data, "photo": att_url}
                        api_url = f"{base_url}{url_part}"
                        response = requests.post(api_url, json=payload, timeout=10)
                    elif att_type == "video":
                        url_part = "/sendVideo"
                        tmp_path = _download_to_temp(att_url)
                        if tmp_path:
                            try:
                                api_url = f"{base_url}{url_part}"
                                with open(tmp_path, "rb") as f:
                                    files = {"video": (_extract_filename_from_url(att_url), f)}
                                    response = requests.post(api_url, data=form_data, files=files, timeout=60)
                            finally:
                                os.remove(tmp_path)
                        else:
                            # Fallback: try URL directly
                            payload = {**form_data, "video": att_url}
                            api_url = f"{base_url}{url_part}"
                            response = requests.post(api_url, json=payload, timeout=10)
                    elif att_type == "audio":
                        url_part = "/sendAudio"
                        tmp_path = _download_to_temp(att_url)
                        if tmp_path:
                            try:
                                api_url = f"{base_url}{url_part}"
                                with open(tmp_path, "rb") as f:
                                    files = {"audio": (_extract_filename_from_url(att_url), f)}
                                    response = requests.post(api_url, data=form_data, files=files, timeout=60)
                            finally:
                                os.remove(tmp_path)
                        else:
                            payload = {**form_data, "audio": att_url}
                            api_url = f"{base_url}{url_part}"
                            response = requests.post(api_url, json=payload, timeout=10)
                    else:
                        # file / document — must upload via multipart/form-data
                        url_part = "/sendDocument"
                        tmp_path = _download_to_temp(att_url)
                        if tmp_path:
                            try:
                                api_url = f"{base_url}{url_part}"
                                with open(tmp_path, "rb") as f:
                                    files = {"document": (_extract_filename_from_url(att_url), f)}
                                    response = requests.post(api_url, data=form_data, files=files, timeout=60)
                            finally:
                                os.remove(tmp_path)
                        else:
                            # Fallback: try URL directly
                            payload = {**form_data, "document": att_url}
                            api_url = f"{base_url}{url_part}"
                            response = requests.post(api_url, json=payload, timeout=10)

                    response.raise_for_status()
                    last_response = response.json()
                logger.info("Successfully sent Telegram attachment messages.")
                return last_response or {}

        except RequestException as e:
            # Log the response body for debugging
            resp_body = ""
            if hasattr(e, "response") and e.response is not None:
                try:
                    resp_body = e.response.text
                except Exception:
                    pass
            logger.error(
                "Failed to send Telegram message. Data: %s, Error: %s, Response: %s",
                _mask_token(data),
                str(e),
                resp_body,
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
        reply_to = data.get("reply_to")
        if reply_to:
            payload["quote"] = {"globalMsgId": str(reply_to)}

        # Mention support: convert to zca-js format {pos, uid, len}
        mentions = data.get("mentions")
        if mentions:
            payload["mentions"] = _build_zalo_mentions(mentions)

        attachments = data.get("attachments")
        if attachments:
            payload["attachments"] = [
                att.get("url") for att in attachments if att.get("url")
            ]

        try:
            logger.info("Sending Zalo payload: %s", payload)
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            logger.info("Successfully sent message via external API.")
            return response.json()
        except RequestException as e:
            # Log response body for debugging
            resp_body = ""
            if hasattr(e, "response") and e.response is not None:
                try:
                    resp_body = e.response.text
                except Exception:
                    pass
            logger.error(
                "Failed to send message via external API. URL: %s, Error: %s, Response: %s",
                url,
                str(e),
                resp_body,
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

                    # Mention support: add mentions JIDs to first media message
                    mentions = data.get("mentions")
                    if i == 0 and mentions:
                        baileys_msg["mentions"] = _build_whatsapp_mentions(mentions)

                    payload = {
                        "message": baileys_msg,
                        "threadId": conv_id,
                        "type": msg_type,
                    }
                    # Reply support: only attach quotedMessageId on first media
                    reply_to = data.get("reply_to")
                    if i == 0 and reply_to:
                        payload["quotedMessageId"] = str(reply_to)
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
                # Mention support: pass mentions JIDs for Baileys
                mentions = data.get("mentions")
                if mentions:
                    payload["mentions"] = _build_whatsapp_mentions(mentions)
                # Reply support
                reply_to = data.get("reply_to")
                if reply_to:
                    payload["quotedMessageId"] = str(reply_to)
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
