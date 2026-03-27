import logging
import requests
from typing import Dict, Any
import config

logger = logging.getLogger(__name__)

def get_zalo_accounts():
    url = f"{config.ZALO_EXTERNAL_API_BASE}/api/accounts"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.json()

def create_zalo_account(bot_id: str):
    url = f"{config.ZALO_EXTERNAL_API_BASE}/api/accounts"
    response = requests.post(url, json={"accountId": bot_id}, timeout=10)
    response.raise_for_status()
    return response.json()

def config_zalo_webhook(bot_id: str, base_url: str):
    url = f"{config.ZALO_EXTERNAL_API_BASE}/api/{bot_id}/webhook-config"
    webhook_url = f"{base_url}/api/hook?platform=zalo"
    response = requests.post(url, json={"webhookUrl": webhook_url}, timeout=10)
    response.raise_for_status()
    return response.json()

def get_zalo_webhook_config(bot_id: str):
    url = f"{config.ZALO_EXTERNAL_API_BASE}/api/{bot_id}/webhook-config"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.json()

def sync_zalo_webhook(bot_id: str, base_url: str):
    """Checks if the Zalo account exists and webhook matches the current base_url."""
    current_webhook = f"{base_url}/api/hook?platform=zalo"
    try:
        # 1. Check if account exists
        accounts = get_zalo_accounts()
        account_exists = any(str(acc.get("accountId")) == str(bot_id) for acc in accounts)

        if not account_exists:
            logger.info(f"Zalo account {bot_id} not found, creating...")
            create_zalo_account(bot_id)

        # 2. Check/Update webhook config
        try:
            webhook_info = get_zalo_webhook_config(bot_id)
            if webhook_info.get("webhookUrl") != current_webhook:
                logger.info(f"Updating Zalo webhook for {bot_id} to {current_webhook}")
                config_zalo_webhook(bot_id, base_url)
        except Exception:
            logger.info(f"Setting initial Zalo webhook for {bot_id}")
            config_zalo_webhook(bot_id, base_url)

    except Exception as e:
        logger.error(f"Failed to sync Zalo webhook for {bot_id}: {e}")
        raise

def get_zalo_status(bot_id: str):
    url = f"{config.ZALO_EXTERNAL_API_BASE}/api/{bot_id}/status"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.json()

def get_zalo_qr_code(bot_id: str):
    url = f"{config.ZALO_EXTERNAL_API_BASE}/qr/{bot_id}.png"
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    return response.content
