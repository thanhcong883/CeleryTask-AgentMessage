#!/bin/bash
# =============================================================================
# Test Reply Message Feature
# =============================================================================
# Cách dùng:
#   chmod +x test_reply.sh
#   ./test_reply.sh [whatsapp|zalo|telegram|celery]
#
# Nếu không truyền argument, sẽ chạy tất cả tests.
# =============================================================================

set -e

# --- Config ---
CELERY_BASE="http://localhost:8000"
ZALO_API_BASE="http://123.30.233.74:5000"
WHATSAPP_API_BASE="https://api-whatapp-dev.r.evgcloud.net"
HOOK_TOKEN="HookToken222"

# --- Placeholder IDs (thay bằng giá trị thật khi test) ---
WHATSAPP_ACCOUNT_ID="your_whatsapp_account_id"
WHATSAPP_THREAD_ID="628123456789"           # số điện thoại hoặc JID
WHATSAPP_QUOTED_MSG_ID="3EB0A1B2C3D4E5F6"  # message ID cần reply

ZALO_ACCOUNT_ID="your_zalo_account_id"
ZALO_THREAD_ID="6643573306424440690"        # user ID hoặc group ID
ZALO_QUOTED_MSG_ID="7676592750243"          # msgId từ Zalo

TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
TELEGRAM_CHAT_ID="-5236384276"              # group hoặc user chat ID
TELEGRAM_REPLY_MSG_ID="77"                  # message_id cần reply

# Colors
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# =============================================================================
# 1. Test WhatsApp (baileys2api) - Reply text
# =============================================================================
test_whatsapp_reply_text() {
    echo -e "${CYAN}━━━ [WhatsApp] Reply Text Message ━━━${NC}"
    curl -s -X POST "${WHATSAPP_API_BASE}/api/${WHATSAPP_ACCOUNT_ID}/send" \
      -H "Content-Type: application/json" \
      -d '{
        "text": "Đây là tin nhắn reply test 🔁",
        "threadId": "'"${WHATSAPP_THREAD_ID}"'",
        "type": "user",
        "quotedMessageId": "'"${WHATSAPP_QUOTED_MSG_ID}"'"
      }' | python3 -m json.tool 2>/dev/null || echo "(no json response)"
    echo ""
}

# =============================================================================
# 2. Test WhatsApp (baileys2api) - Reply with image
# =============================================================================
test_whatsapp_reply_image() {
    echo -e "${CYAN}━━━ [WhatsApp] Reply with Image ━━━${NC}"
    curl -s -X POST "${WHATSAPP_API_BASE}/api/${WHATSAPP_ACCOUNT_ID}/send" \
      -H "Content-Type: application/json" \
      -d '{
        "message": {
          "image": {"url": "https://via.placeholder.com/300"},
          "caption": "Reply kèm ảnh 📷"
        },
        "threadId": "'"${WHATSAPP_THREAD_ID}"'",
        "type": "user",
        "quotedMessageId": "'"${WHATSAPP_QUOTED_MSG_ID}"'"
      }' | python3 -m json.tool 2>/dev/null || echo "(no json response)"
    echo ""
}

# =============================================================================
# 3. Test Zalo (zca2api) - Reply text
# =============================================================================
test_zalo_reply_text() {
    echo -e "${CYAN}━━━ [Zalo] Reply Text Message ━━━${NC}"
    curl -s -X POST "${ZALO_API_BASE}/api/${ZALO_ACCOUNT_ID}/send" \
      -H "Content-Type: application/json" \
      -d '{
        "text": "Đây là tin nhắn reply Zalo test 🔁",
        "threadId": "'"${ZALO_THREAD_ID}"'",
        "type": "user",
        "quote": {
          "globalMsgId": "'"${ZALO_QUOTED_MSG_ID}"'"
        }
      }' | python3 -m json.tool 2>/dev/null || echo "(no json response)"
    echo ""
}

# =============================================================================
# 4. Test Zalo (zca2api) - Reply with attachment
# =============================================================================
test_zalo_reply_attachment() {
    echo -e "${CYAN}━━━ [Zalo] Reply with Attachment ━━━${NC}"
    curl -s -X POST "${ZALO_API_BASE}/api/${ZALO_ACCOUNT_ID}/send" \
      -H "Content-Type: application/json" \
      -d '{
        "text": "Reply kèm ảnh Zalo 📷",
        "threadId": "'"${ZALO_THREAD_ID}"'",
        "type": "user",
        "attachments": ["https://via.placeholder.com/300"],
        "quote": {
          "globalMsgId": "'"${ZALO_QUOTED_MSG_ID}"'"
        }
      }' | python3 -m json.tool 2>/dev/null || echo "(no json response)"
    echo ""
}

# =============================================================================
# 5. Test Telegram - Reply text (gọi trực tiếp Telegram Bot API)
# =============================================================================
test_telegram_reply_text() {
    echo -e "${CYAN}━━━ [Telegram] Reply Text Message ━━━${NC}"
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
      -H "Content-Type: application/json" \
      -d '{
        "chat_id": "'"${TELEGRAM_CHAT_ID}"'",
        "text": "Đây là tin nhắn reply Telegram test 🔁",
        "reply_to_message_id": '"${TELEGRAM_REPLY_MSG_ID}"'
      }' | python3 -m json.tool 2>/dev/null || echo "(no json response)"
    echo ""
}

# =============================================================================
# 6. Test qua Celery (CeleryTask) - gửi qua FastAPI endpoint
#    Giả lập gọi send_message task thông qua API hook hoặc trực tiếp
# =============================================================================
test_celery_whatsapp_reply() {
    echo -e "${CYAN}━━━ [Celery → WhatsApp] Reply via send_message task ━━━${NC}"
    echo -e "${YELLOW}Python script (chạy trong môi trường có Celery):${NC}"
    cat << 'PYTHON'
from tasks import send_message

data = {
    "platform_name": "Whatsapp",
    "content": "Reply từ Celery → WhatsApp 🔁",
    "type": "user",
    "user_id": "628123456789",
    "bot_id": "your_whatsapp_account_id",
    "reply_to_message_id": "3EB0A1B2C3D4E5F6",
}
send_message.apply_async(args=(data, "admin"), queue="celery_send_message")
PYTHON
    echo ""
}

test_celery_zalo_reply() {
    echo -e "${CYAN}━━━ [Celery → Zalo] Reply via send_message task ━━━${NC}"
    echo -e "${YELLOW}Python script (chạy trong môi trường có Celery):${NC}"
    cat << 'PYTHON'
from tasks import send_message

data = {
    "platform_name": "Zalo",
    "content": "Reply từ Celery → Zalo 🔁",
    "type": "user",
    "user_id": "6643573306424440690",
    "bot_id": "your_zalo_account_id",
    "reply_to_message_id": "7676592750243",
}
send_message.apply_async(args=(data, "admin"), queue="celery_send_message")
PYTHON
    echo ""
}

test_celery_telegram_reply() {
    echo -e "${CYAN}━━━ [Celery → Telegram] Reply via send_message task ━━━${NC}"
    echo -e "${YELLOW}Python script (chạy trong môi trường có Celery):${NC}"
    cat << 'PYTHON'
from tasks import send_message

data = {
    "platform_name": "Telegram",
    "content": "Reply từ Celery → Telegram 🔁",
    "type": "group",
    "group_id": "-5236384276",
    "token": "your_telegram_bot_token",
    "reply_to_message_id": "77",
}
send_message.apply_async(args=(data, "admin"), queue="celery_send_message")
PYTHON
    echo ""
}

# =============================================================================
# Run
# =============================================================================
echo -e "${GREEN}╔══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Test Reply Message Feature         ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════╝${NC}"
echo ""

case "${1:-all}" in
    whatsapp)
        test_whatsapp_reply_text
        test_whatsapp_reply_image
        ;;
    zalo)
        test_zalo_reply_text
        test_zalo_reply_attachment
        ;;
    telegram)
        test_telegram_reply_text
        ;;
    celery)
        test_celery_whatsapp_reply
        test_celery_zalo_reply
        test_celery_telegram_reply
        ;;
    all)
        test_whatsapp_reply_text
        test_whatsapp_reply_image
        test_zalo_reply_text
        test_zalo_reply_attachment
        test_telegram_reply_text
        echo -e "${GREEN}━━━ Celery Python Scripts ━━━${NC}"
        test_celery_whatsapp_reply
        test_celery_zalo_reply
        test_celery_telegram_reply
        ;;
    *)
        echo "Usage: $0 [whatsapp|zalo|telegram|celery|all]"
        exit 1
        ;;
esac

echo -e "${GREEN}✅ Done!${NC}"
