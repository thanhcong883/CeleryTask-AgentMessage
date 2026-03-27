import logging
from fastapi import APIRouter, HTTPException, Request, Query
from models import GenericResponse
from database import redis_client
from telegram_service import store_received_message
from tasks import process_message

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/hook", tags=["Webhooks"])

@router.post("", response_model=GenericResponse, summary="Zalo message hook")
async def zalo_hook(
    request: Request,
    platform: str = Query("zalo", description="The platform type (currently only zalo supported)")
):
    """
    Webhook endpoint to receive messages from Zalo.
    Messages are formatted and pushed to a Celery task for processing.
    """
    if platform != "zalo":
         raise HTTPException(status_code=400, detail="Only Zalo platform supported on this hook")

    body = await request.json()
    logger.info(f"Received Zalo hook: {body}")

    bot_id = body.get("accountId")
    if not bot_id:
        # Fallback to older nested structure if needed, but primary is accountId
        data_field = body.get("data", {})
        bot_id = data_field.get("idTo")

    bot_config = redis_client.hgetall(f"bot_config:{bot_id}")
    token = bot_config.get("token") if bot_config else None

    # Determine message type and identifiers
    raw_data = body.get("raw", {}).get("data", {})
    is_group = body.get("isGroup", False)
    msg_type = "group" if is_group else "private"

    # Use raw fields as primary source of truth if available
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

    store_received_message(msg_data)
    process_message.delay(msg_data)
    return {"status": "ok"}
