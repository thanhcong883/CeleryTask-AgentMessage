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
        "token": "tdWIGTogr6ZOUXD1tQtVQDnt6KRLkw0pWmWAGDAkj6YnBJS3wgAmVUCk5WEMdgrTrZ1gCBwKsd_y3rOpfTliTgnqRmtlr_OYbtfNJVAWxJU834bSuBtx1RubOdplbzXNap911kRYsckUTXX5sUEcC8PpOXdNozf3hrvL7_N9zc-AT6v6ml_2Riij1qIK_iGt_aLp7hZmo4Bj858OZU_jITnhT3Irpl5XqKio797i_apqPraUeloPTi9G1YsJWhq6sXS-B8p4htxIJozIaSkA1Uj6JIs_wkXdlc1CGE2qwZUf57v6qOVvEg8JRsxsXCueWnnsHE6gzo-XFsbKexVjUA4K8HBYiPjXXm9SBewGqLdBEtCgkBZ-Lj8RKYZKZir5WmHo8-oKld-xD78aqQ_HMDSaOoCmH33YzH_QjDHf"
    }
}