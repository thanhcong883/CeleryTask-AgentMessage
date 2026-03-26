"""Configuration file for Celery tasks and API endpoints."""

import os
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Redis Configuration
REDIS_HOST: Optional[str] = os.getenv("REDIS_HOST")
REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD")
REDIS_USER: Optional[str] = os.getenv("REDIS_USER")
REDIS_PORT: Optional[str] = os.getenv("REDIS_PORT")
REDIS_URL: str = os.getenv(
    "REDIS_URL", f"redis://{REDIS_USER}:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/3"
)

# Strapi API Endpoints
STRAPI_API_BASE: Optional[str] = os.getenv("STRAPI_API_BASE")
STRAPI_ACCOUNT: str = f"{STRAPI_API_BASE}/accounts"
STRAPI_CONVERSATION: str = f"{STRAPI_API_BASE}/conversations"
STRAPI_CONVERSATION_MEMBER: str = f"{STRAPI_API_BASE}/conversation-members"
STRAPI_CUSTOMER: str = f"{STRAPI_API_BASE}/customers"
STRAPI_MESSAGE: str = f"{STRAPI_API_BASE}/messages"
STRAPI_PLATFORM: str = f"{STRAPI_API_BASE}/platforms"
STRAPI_TOKEN: Optional[str] = os.getenv("STRAPI_TOKEN")

STRAPI_UPDATE_MESSAGE: str = f"{STRAPI_API_BASE}/agent-chat-box/webhook/message-status"
STRAPI_SYNC_MESSAGE: str = f"{STRAPI_API_BASE}/agent-chat-box/webhook/sync-message"
STRAPI_GET_CONVERSATION: str = f"{STRAPI_API_BASE}/agent-chat-box/webhook/conversation"
STRAPI_GET_HISTORY_MESSAGE: str = (
    f"{STRAPI_API_BASE}/agent-chat-box/webhook/conversation/{{conversation_id}}/messages?mess_id={{message_id}}"
)
STRAPI_SAVE_MESSAGE_BOT_SENT: str = (
    f"{STRAPI_API_BASE}/agent-chat-box/webhook/bot-reply"
)
STRAPI_GET_CONVERSATION_MEMBER: str = (
    f"{STRAPI_API_BASE}/agent-chat-box/webhook/conversations/{{conversation_id}}/members"
)

# N8N Configuration
N8N_AGENT_WEBHOOK: Optional[str] = os.getenv("N8N_AGENT_WEBHOOK")
CHECK_QUESTION_API: Optional[str] = os.getenv("CHECK_QUESTION_API")

# External Zalo API Base
ZALO_EXTERNAL_API_BASE: str = os.getenv("ZALO_EXTERNAL_API_BASE", "http://abc.com")
BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")

# Headers
HEADERS_STRAPI: Dict[str, Optional[str]] = {
    "Authorization": STRAPI_TOKEN,
    "Content-Type": "application/json",
}

HEADERS_API_BACKEND: Dict[str, Optional[str]] = {
    "Content-Type": "application/json",
    "x-webhook-secret": os.getenv("WEBHOOK_SECRET"),
    "Authorization": STRAPI_TOKEN,
}

# Platform Configurations
PLATFORMS: Dict[str, Dict[str, str]] = {
    "Telegram": {
        "url": "https://api.telegram.org/bot{token}/sendMessage",
    },
    "Zalo": {
        "private_url": "https://openapi.zalo.me/v3.0/oa/message/cs",
        "group_url": "https://openapi.zalo.me/v3.0/oa/group/message",
    },
}
