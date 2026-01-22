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
STRAPI_TOKEN = "Bearer 40ccabda9b71ee3e776367acd971dcd3f6e759b4439c3e14d78ca7e88a20504dbde0c1260fb71aa5590152c75cf163c888aba5b8c6e724a79ae508b3eac0b8aed09929e3884e24cb00a22154bee4bd8a5dc0a92f3c7e69416fb6b675c1a7f1a3350cca172f570681ea99bc9ec916f4791709dd768a65975d125bb12d6c9ab905"
STRAPI_UPDATE_MESSAGE = "http://localhost:1337/api/agent-chat-box/webhook/message-status"
STRAPI_SYNC_MESSAGE = "http://localhost:1337/api/agent-chat-box/webhook/sync-message"
STRAPI_GET_CONVERSATION = "http://localhost:1337/api/agent-chat-box/webhook/conversation"
STRAPI_GET_HISTORY_MESSAGE = "http://localhost:1337/api/agent-chat-box/webhook/conversation/{conversation_id}/messages?mess_id={message_id}"

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
    "x-webhook-secret": "k7P2mR9vX4"
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
        "token": "x35o0Lr-k13gCtC1N7cp4Eu-UGPKR-znbNjE16PyzNkAUsGbLaRyUf9_CmbXIhrgjt8R17jiX4csAoGBJJhg6Qe4Utr55gySzWyQ5ZivbKdS43HT2p2l7UmvFsus3OT_xpCf7beyYdsE9aGYQXZILx0KJ41x9U8ngWvwLNCwjn2o9ZzUKc6V0wHqCXngGQThcMO9V5bIg0-3JpbjJdduUhbhQHjbPU1QZorB6481vLI44d4qL5NuUvrbSt5rVBzbk4q_EtrMZp6fO4zSVoZHFyG7ItmkJFuOmbLlN01xfWhnJW1_6WAtOVCA2nyq1y1DrKnp009NnMB0RWec2bMXTBX8DmPQK_POx61yI1XUy273SsDd8qIjUEve63mtOhTUZ30_4LWey5sOEMj8L7JL1vzbMt9RN_82Wt_v9rjWk14"
    }
}