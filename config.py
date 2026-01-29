"""Configuration file for Celery tasks and API endpoints."""

# Redis Configuration
REDIS_HOST = "redis.evgcloud.local"
REDIS_PASSWORD = "redispass"
REDIS_USER = "default"
REDIS_PORT = 6379
REDIS_URL = f"redis://{REDIS_USER}:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/3"

# Strapi API Endpoints
STRAPI_ACCOUNT = "http://localhost:1337/api/accounts"
STRAPI_CONVERSATION = "http://localhost:1337/api/conversations"
STRAPI_CONVERSATION_MEMBER = "http://localhost:1337/api/conversation-members"
STRAPI_CUSTOMER = "http://localhost:1337/api/customers"
STRAPI_MESSAGE = "http://localhost:1337/api/messages"
STRAPI_PLATFORM = "http://localhost:1337/api/platforms"
STRAPI_TOKEN = "Bearer 9e0b950d782cfe7f1b70a3b8f1e6ca77f9eb997f168e747d4da8c88b1293e9ca8cc5a43425b3990454dc976d6853a9dbf38db80f5c0d63d9e5aad314fee43f91e46f6bce6113cf67c866822f1fae3ff5db364be9022c6902f98dbfa72df8026d68460e152c17720c2c8d9b842e417f54090f33e0585c4f1a30b493fb4d9fe9d8"
STRAPI_UPDATE_MESSAGE = "http://localhost:1337/api/agent-chat-box/webhook/message-status"
STRAPI_SYNC_MESSAGE = "http://localhost:1337/api/agent-chat-box/webhook/sync-message"
STRAPI_GET_CONVERSATION = "http://localhost:1337/api/agent-chat-box/webhook/conversation"
STRAPI_GET_HISTORY_MESSAGE = "http://localhost:1337/api/agent-chat-box/webhook/conversation/{conversation_id}/messages?mess_id={message_id}"
STRAPI_SAVE_MESSAGE_BOT_SENT = "http://localhost:1337/api/agent-chat-box/webhook/bot-reply"
STRAPI_GET_CONVERSATION_MEMBER = "http://localhost:1337/api/agent-chat-box/webhook/conversations/{conversation_id}/members"
# N8N Configuration
N8N_AGENT_WEBHOOK = "https://agent-dev.data.irsocial.vn/webhook/2e346872-f386-4168-a7fb-220025a4e13b"
CHECK_QUESTION_API = "https://agent-dev.data.irsocial.vn/webhook/5ccc728b-fc10-4ee5-9753-adf5ecca503f"

# Headers
HEADERS_STRAPI = {
    "Authorization": STRAPI_TOKEN,
    "Content-Type": "application/json"
}

HEADERS_API_BACKEND = {
    "Content-Type": "application/json",
    "x-webhook-secret": "k7P2mR9vX4",
    "Authorization": STRAPI_TOKEN
}

# Platform Configurations
PLATFORMS = {
    "8": {
        "url": "https://api.telegram.org/bot{token}/sendMessage",
        "token": "8590498795:AAGf9pfn-eJnnBPyXzVFL_u0aXG9SVPwrHU"
    },
    "7": {
        "private_url": "https://openapi.zalo.me/v3.0/oa/message/cs",
        "group_url": "https://openapi.zalo.me/v3.0/oa/group/message",
        "token": "5R_K0WK5D2WJlTK2108_A1UmtmKC54yeV_R31ZTFKcbtzy00CX8YB7tTem8J6HXFHAI36Z9c7dGcgBG6PXfGKodzmIecCa17Iz71BrXZSqO3YE4qTN9s6ngip4z_S2rb5P-w7r1i8KyvfCHYVbXm21YNcaq3P7uWKh76J3nh929MsQ5900nADalBo4G3UNPXTi7mJZbz40Wehgz3OnDA5WtZgNn7E3adDT-cLIOb7Y9GsOLp2njdDsEbn5fnMr1qOv_84HPwAZXMdQDAH48A9GYWdtTiSnWd7A2COdf52p4vYE5zQLTdBHZmt4L04r1f0yR9E6Ca8cqrouWxSMmH4GUNbcjwJmH57_EPEb0W5M0-vOqnPXzg7Y3Qr4LeDaOqEF2YGcbN8mOgawDfPZG9GZQJwMvvIYAAqnm36pGf"
    }
}
