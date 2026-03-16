import logging
import requests
import config

# Configure logging
logger = logging.getLogger(__name__)


class TelegramProvider:
    def send(self, data):
        conf = config.PLATFORMS["1"]
        url = conf["url"].format(token=conf["token"])
        payload = {
            "chat_id": data.get("group_id")
            if data.get("type") in ["group", "supergroup"]
            else data.get("user_id"),
            "text": data.get("content"),
        }
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to send Telegram message: {e}")
            raise


class ZaloProvider:
    def send(self, data):
        logger.info(f"Gửi tin nhắn Zalo với dữ liệu: {data}")
        conf = config.PLATFORMS["2"]
        # Safely handle missing or None type
        msg_type = str(data.get("type", "")).strip()
        is_private = msg_type == "private"
        url = conf["private_url"] if is_private else conf["group_url"]
        headers = {"access_token": conf["token"]}
        payload = {
            "recipient": {
                "user_id" if is_private else "group_id": data.get(
                    "user_id" if is_private else "group_id"
                )
            },
            "message": {"text": data.get("content")},
        }
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to send Zalo message: {e}")
            raise


PROVIDERS = {"1": TelegramProvider(), "2": ZaloProvider()}
