"""Configuration file for Celery tasks and API endpoints."""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Redis Configuration
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
REDIS_USER = os.getenv("REDIS_USER")
REDIS_PORT = os.getenv("REDIS_PORT")
REDIS_URL = os.getenv(
    "REDIS_URL", f"redis://{REDIS_USER}:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/3"
)

# Strapi API Endpoints
STRAPI_API_BASE = os.getenv("STRAPI_API_BASE")
STRAPI_ACCOUNT = f"{STRAPI_API_BASE}/accounts"
STRAPI_CONVERSATION = f"{STRAPI_API_BASE}/conversations"
STRAPI_CONVERSATION_MEMBER = f"{STRAPI_API_BASE}/conversation-members"
STRAPI_CUSTOMER = f"{STRAPI_API_BASE}/customers"
STRAPI_MESSAGE = f"{STRAPI_API_BASE}/messages"
STRAPI_PLATFORM = f"{STRAPI_API_BASE}/platforms"
STRAPI_TOKEN = os.getenv("STRAPI_TOKEN")
STRAPI_UPDATE_MESSAGE = f"{STRAPI_API_BASE}/agent-chat-box/webhook/message-status"
STRAPI_SYNC_MESSAGE = f"{STRAPI_API_BASE}/agent-chat-box/webhook/sync-message"
STRAPI_GET_CONVERSATION = f"{STRAPI_API_BASE}/agent-chat-box/webhook/conversation"
STRAPI_GET_HISTORY_MESSAGE = f"{STRAPI_API_BASE}/agent-chat-box/webhook/conversation/{{conversation_id}}/messages?mess_id={{message_id}}"
STRAPI_SAVE_MESSAGE_BOT_SENT = f"{STRAPI_API_BASE}/agent-chat-box/webhook/bot-reply"
STRAPI_GET_CONVERSATION_MEMBER = f"{STRAPI_API_BASE}/agent-chat-box/webhook/conversations/{{conversation_id}}/members"

# N8N Configuration
N8N_AGENT_WEBHOOK = os.getenv("N8N_AGENT_WEBHOOK")
CHECK_QUESTION_API = os.getenv("CHECK_QUESTION_API")

# Headers
HEADERS_STRAPI = {"Authorization": STRAPI_TOKEN, "Content-Type": "application/json"}

HEADERS_API_BACKEND = {
    "Content-Type": "application/json",
    "x-webhook-secret": os.getenv("WEBHOOK_SECRET"),
    "Authorization": STRAPI_TOKEN,
}

