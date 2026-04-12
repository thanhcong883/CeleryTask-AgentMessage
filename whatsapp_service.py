import logging
import requests
from typing import Dict, Any
import config

logger = logging.getLogger(__name__)

def get_whatsapp_accounts():
    url = f"{config.WHATSAPP_EXTERNAL_API_BASE}/api/accounts"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.json()

def create_whatsapp_account(bot_id: str):
    url = f"{config.WHATSAPP_EXTERNAL_API_BASE}/api/accounts"
    response = requests.post(url, json={"accountId": bot_id}, timeout=10)
    response.raise_for_status()
    return response.json()

def config_whatsapp_webhook(bot_id: str, base_url: str):
    url = f"{config.WHATSAPP_EXTERNAL_API_BASE}/api/{bot_id}/webhook-config"
    webhook_url = f"{base_url}/api/hook?platform=whatsapp&secretToken={config.HOOK_TOKEN}"
    response = requests.post(url, json={"webhookUrl": webhook_url, "secretToken": config.HOOK_TOKEN}, timeout=10)
    response.raise_for_status()
    return response.json()

def get_whatsapp_webhook_config(bot_id: str):
    url = f"{config.WHATSAPP_EXTERNAL_API_BASE}/api/{bot_id}/webhook-config"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.json()

def sync_whatsapp_webhook(bot_id: str, base_url: str):
    """Checks if the WhatsApp account exists and webhook matches the current base_url."""
    current_webhook = f"{base_url}/api/hook?platform=whatsapp&secretToken={config.HOOK_TOKEN}"
    try:
        # 1. Check if account exists
        accounts = get_whatsapp_accounts()
        account_exists = any(str(acc.get("accountId")) == str(bot_id) for acc in accounts)

        if not account_exists:
            logger.info(f"WhatsApp account {bot_id} not found, creating...")
            create_whatsapp_account(bot_id)

        # 2. Check/Update webhook config
        try:
            webhook_info = get_whatsapp_webhook_config(bot_id)
            if webhook_info.get("webhookUrl") != current_webhook:
                logger.info(f"Updating WhatsApp webhook for {bot_id} to {current_webhook}")
                config_whatsapp_webhook(bot_id, base_url)
        except Exception:
            logger.info(f"Setting initial WhatsApp webhook for {bot_id}")
            config_whatsapp_webhook(bot_id, base_url)

    except Exception as e:
        logger.error(f"Failed to sync WhatsApp webhook for {bot_id}: {e}")
        raise

def get_whatsapp_status(bot_id: str):
    url = f"{config.WHATSAPP_EXTERNAL_API_BASE}/api/{bot_id}/status"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.json()

def get_whatsapp_qr_code(bot_id: str):
    url = f"{config.WHATSAPP_EXTERNAL_API_BASE}/qr/{bot_id}.png"
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    return response.content
