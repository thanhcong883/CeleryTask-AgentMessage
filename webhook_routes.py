import logging
from fastapi import APIRouter, HTTPException, Request, Query
from models import GenericResponse
from database import redis_client
from telegram_service import store_received_message
from tasks import process_message

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/hook", tags=["Webhooks"])

@router.post("", response_model=GenericResponse, summary="Universal message hook")
async def universal_hook(
    request: Request,
    platform: str = Query("zalo", description="The platform type (zalo, telegram)"),
    bot_id: str = Query(None, description="The bot ID (required for telegram)")
):
    """
    Webhook endpoint to receive messages from various platforms.
    Messages are formatted and pushed to a Celery task for processing.
    """
    body = await request.json()
    logger.info(f"Received {platform} hook: {body}")

    if platform == "zalo":
        received_bot_id = body.get("accountId")
        if not received_bot_id:
            data_field = body.get("data", {})
            received_bot_id = data_field.get("idTo")

        bot_config = redis_client.hgetall(f"bot_config:{received_bot_id}")
        token = bot_config.get("token") if bot_config else None

        raw_data = body.get("raw", {}).get("data", {})
        is_group = body.get("isGroup", False)
        msg_type = "group" if is_group else "private"

        content = raw_data.get("content") or body.get("text")
        sender_id = raw_data.get("uidFrom") or body.get("from")
        conv_id = body.get("threadId") or raw_data.get("idTo")

        msg_data = {
            "platform_name": "Zalo",
            "content": content,
            "platform_user_id": sender_id,
            "platform_conv_id": conv_id,
            "token": token,
            "type": msg_type,
        }
    elif platform == "telegram":
        if not bot_id:
             # Try to find bot_id if not provided in query (though we set it in sync)
             logger.warning("Telegram hook received without bot_id query parameter")

        bot_config = redis_client.hgetall(f"bot_config:{bot_id}")
        token = bot_config.get("token") if bot_config else None

        # Telegram Update parsing
        message = body.get("message") or body.get("edited_message")
        if not message or "text" not in message:
            return {"status": "ok", "message": "No text message to process"}

        chat = message.get("chat", {})
        from_user = message.get("from", {})
        msg_type = "private" if chat.get("type") == "private" else "group"

        msg_data = {
            "platform_name": "Telegram",
            "content": message.get("text"),
            "platform_user_id": str(from_user.get("id")),
            "platform_conv_id": str(chat.get("id")),
            "token": token,
            "type": msg_type,
        }
    else:
         raise HTTPException(status_code=400, detail=f"Platform {platform} not supported on this hook")

    store_received_message(msg_data)
    process_message.delay(msg_data)
    return {"status": "ok"}
