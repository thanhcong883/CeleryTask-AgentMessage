import os
from dotenv import load_dotenv
import json

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
STRAPI_GET_HISTORY_MESSAGE = os.getenv("STRAPI_GET_HISTORY_MESSAGE")
N8N_AGENT_WEBHOOK = os.getenv("N8N_AGENT_WEBHOOK")
CHECK_QUESTION_API = os.getenv("CHECK_QUESTION_API")
STRAPI_SYNC_MESSAGE = os.getenv("STRAPI_SYNC_MESSAGE")
STRAPI_GET_CONVERSATION_MEMBER = os.getenv("STRAPI_GET_CONVERSATION_MEMBER")
STRAPI_GET_CONVERSATION = os.getenv("STRAPI_GET_CONVERSATION")
STRAPI_UPDATE_MESSAGE = os.getenv("STRAPI_UPDATE_MESSAGE")
STRAPI_SAVE_MESSAGE_BOT_SENT = os.getenv("STRAPI_SAVE_MESSAGE_BOT_SENT")

# Headers
try:
    HEADERS_API_BACKEND = json.loads(os.getenv("HEADERS_API_BACKEND", "{}"))
except json.JSONDecodeError:
    HEADERS_API_BACKEND = {}

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
