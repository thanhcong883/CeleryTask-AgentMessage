#!/bin/bash
# =============================================================================
# Test Mention/Tag Feature
# =============================================================================
# Cách dùng:
#   chmod +x test_mention.sh
#   ./test_mention.sh [whatsapp|zalo|telegram|celery|all]
#
# Nếu không truyền argument, sẽ chạy tất cả tests.
# =============================================================================

set -e

# --- Config ---
CELERY_BASE="http://localhost:8000"
ZALO_API_BASE="http://123.30.233.74:5000"
WHATSAPP_API_BASE="https://api-whatapp-dev.r.evgcloud.net"

# --- Placeholder IDs (thay bằng giá trị thật khi test) ---
WHATSAPP_ACCOUNT_ID="your_whatsapp_account_id"
WHATSAPP_GROUP_ID="120363123456789@g.us"         # Group JID
WHATSAPP_MENTION_USER="84901234567"               # Phone number to mention

ZALO_ACCOUNT_ID="your_zalo_account_id"
ZALO_GROUP_ID="group_thread_id"                   # Group thread ID
ZALO_MENTION_UID="zalo_user_id_to_mention"        # Zalo UID to mention

TELEGRAM_BOT_ID="your_telegram_bot_id"
TELEGRAM_GROUP_ID="-5236384276"                   # Group chat ID
TELEGRAM_MENTION_USER_ID="123456789"              # Telegram user ID to mention

# Colors
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# =============================================================================
# 1. Test WhatsApp (baileys2api) - Mention in text
# =============================================================================
test_whatsapp_mention_text() {
    echo -e "${CYAN}━━━ [WhatsApp] Mention in Text Message ━━━${NC}"
    curl -s -X POST "${WHATSAPP_API_BASE}/api/${WHATSAPP_ACCOUNT_ID}/send" \
      -H "Content-Type: application/json" \
      -d '{
        "text": "Hello @'"${WHATSAPP_MENTION_USER}"', bạn khỏe không? 👋",
        "threadId": "'"${WHATSAPP_GROUP_ID}"'",
        "type": "group",
        "mentions": ["'"${WHATSAPP_MENTION_USER}"'@s.whatsapp.net"]
      }' | python3 -m json.tool 2>/dev/null || echo "(no json response)"
    echo ""
}

# =============================================================================
# 2. Test Zalo (zca2api) - Mention in text
# =============================================================================
test_zalo_mention_text() {
    echo -e "${CYAN}━━━ [Zalo] Mention in Text Message ━━━${NC}"
    curl -s -X POST "${ZALO_API_BASE}/api/${ZALO_ACCOUNT_ID}/send" \
      -H "Content-Type: application/json" \
      -d '{
        "text": "Hello @Tên người, bạn khỏe không? 👋",
        "threadId": "'"${ZALO_GROUP_ID}"'",
        "type": "group",
        "mentions": [
          {"pos": 6, "uid": "'"${ZALO_MENTION_UID}"'", "len": 11}
        ]
      }' | python3 -m json.tool 2>/dev/null || echo "(no json response)"
    echo ""
}

# =============================================================================
# 3. Test Telegram - Mention in text (qua Telegram Bot API trực tiếp)
# =============================================================================
test_telegram_mention_text() {
    echo -e "${CYAN}━━━ [Telegram] Mention in Text Message (HTML parse_mode) ━━━${NC}"
    echo -e "${YELLOW}Telegram mentions dùng HTML parse_mode với tg://user link${NC}"
    echo -e "${YELLOW}Ví dụ payload gửi qua CeleryTask:${NC}"
    echo ""
    cat << 'EXAMPLE'
POST /api/bots/{botId}/send
{
  "content": "Hello @John, bạn khỏe không? 👋",
  "group_id": "-5236384276",
  "type": "group",
  "mentions": [
    {"offset": 6, "length": 5, "user_id": "123456789", "display_name": "John"}
  ]
}

→ Telegram API sẽ nhận:
{
  "chat_id": "-5236384276",
  "text": "Hello <a href=\"tg://user?id=123456789\">@John</a>, bạn khỏe không? 👋",
  "parse_mode": "HTML"
}
EXAMPLE
    echo ""
}

# =============================================================================
# 4. Test qua Celery (CeleryTask) - gửi qua FastAPI endpoint /api/bots/{botId}/send
# =============================================================================
test_celery_whatsapp_mention() {
    echo -e "${CYAN}━━━ [Celery → WhatsApp] Mention via API ━━━${NC}"
    curl -s -X POST "${CELERY_BASE}/api/bots/${WHATSAPP_ACCOUNT_ID}/send" \
      -H "Content-Type: application/json" \
      -d '{
        "content": "Hello @'"${WHATSAPP_MENTION_USER}"' bạn khỏe không? 👋",
        "group_id": "'"${WHATSAPP_GROUP_ID}"'",
        "type": "group",
        "mentions": [
          {"offset": 6, "length": '"${#WHATSAPP_MENTION_USER}"', "user_id": "'"${WHATSAPP_MENTION_USER}"'"}
        ]
      }' | python3 -m json.tool 2>/dev/null || echo "(no json response)"
    echo ""
}

test_celery_zalo_mention() {
    echo -e "${CYAN}━━━ [Celery → Zalo] Mention via API ━━━${NC}"
    curl -s -X POST "${CELERY_BASE}/api/bots/${ZALO_ACCOUNT_ID}/send" \
      -H "Content-Type: application/json" \
      -d '{
        "content": "Hello @Tên người bạn khỏe không? 👋",
        "group_id": "'"${ZALO_GROUP_ID}"'",
        "type": "group",
        "mentions": [
          {"offset": 6, "length": 11, "user_id": "'"${ZALO_MENTION_UID}"'", "display_name": "Tên người"}
        ]
      }' | python3 -m json.tool 2>/dev/null || echo "(no json response)"
    echo ""
}

test_celery_telegram_mention() {
    echo -e "${CYAN}━━━ [Celery → Telegram] Mention via API ━━━${NC}"
    curl -s -X POST "${CELERY_BASE}/api/bots/${TELEGRAM_BOT_ID}/send" \
      -H "Content-Type: application/json" \
      -d '{
        "content": "Hello @John bạn khỏe không? 👋",
        "group_id": "'"${TELEGRAM_GROUP_ID}"'",
        "type": "group",
        "mentions": [
          {"offset": 6, "length": 5, "user_id": "'"${TELEGRAM_MENTION_USER_ID}"'", "display_name": "John"}
        ]
      }' | python3 -m json.tool 2>/dev/null || echo "(no json response)"
    echo ""
}

# =============================================================================
# Run
# =============================================================================
echo -e "${GREEN}╔══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Test Mention/Tag Feature           ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════╝${NC}"
echo ""

case "${1:-all}" in
    whatsapp)
        test_whatsapp_mention_text
        ;;
    zalo)
        test_zalo_mention_text
        ;;
    telegram)
        test_telegram_mention_text
        ;;
    celery)
        test_celery_whatsapp_mention
        test_celery_zalo_mention
        test_celery_telegram_mention
        ;;
    all)
        test_whatsapp_mention_text
        test_zalo_mention_text
        test_telegram_mention_text
        echo -e "${GREEN}━━━ Celery API Tests ━━━${NC}"
        test_celery_whatsapp_mention
        test_celery_zalo_mention
        test_celery_telegram_mention
        ;;
    *)
        echo "Usage: $0 [whatsapp|zalo|telegram|celery|all]"
        exit 1
        ;;
esac

echo -e "${GREEN}✅ Done!${NC}"
