from tasks import send_message
import logging
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, Body, Path, Response
from models import CreateBotRequest, BotStatusResponse, GenericResponse, SendMessageRequest
from database import redis_client, get_system_config
from zalo_service import sync_zalo_webhook, get_zalo_status, get_zalo_qr_code
from telegram_service import sync_telegram_webhook, delete_telegram_webhook, get_telegram_webhook_info
import config

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/bots", tags=["Bots"])

@router.get("", summary="List all configured bots")
async def list_bots():
    """Retrieves all bot configurations stored in Redis."""
    try:
        keys = redis_client.keys("bot_config:*")
        bots = []
        for key in keys:
            bot_id = key.split(":")[-1]
            config_data = redis_client.hgetall(key)
            bots.append({"botId": bot_id, "config": config_data})
        return {"status": "ok", "bots": bots}
    except Exception as e:
        logger.error(f"Failed to list bots: {e}")
        raise HTTPException(status_code=500, detail="Database error")

@router.post("", summary="Create a new bot")
async def create_bot(request: CreateBotRequest):
    """
    Initialize a new bot on the specified platform.
    """
    bot_id = str(request.botId)
    bot_config_data = redis_client.hgetall(f"bot_config:{bot_id}")

    current_config = get_system_config()
    base_url = current_config.get("BASE_URL")

    if bot_config_data:
        platform = bot_config_data.get("platform")
        token = bot_config_data.get("token")
        if platform == "zalo":
             sync_zalo_webhook(bot_id, base_url)
        elif platform == "telegram" and token:
             sync_telegram_webhook(bot_id, token, base_url)
        return {"status": "ok", "message": f"Bot {bot_id} already exists and is synced"}

    platform = request.options.platform.lower()
    token = request.options.token

    try:
        redis_client.hset(f"bot_config:{bot_id}", mapping={
            "platform": platform,
            "token": token or ""
        })
    except Exception as e:
        logger.error(f"Failed to save to Redis: {e}")
        raise HTTPException(status_code=500, detail="Database connection error")

    if platform == "telegram":
        if not token:
            raise HTTPException(status_code=400, detail="Token is required for Telegram")
        try:
            sync_telegram_webhook(bot_id, token, base_url)
            return {"status": "ok", "message": "Telegram bot created and webhook configured"}
        except Exception as e:
             logger.error(f"Error creating Telegram bot: {e}")
             raise HTTPException(status_code=500, detail=f"Failed to set Telegram webhook: {str(e)}")

    elif platform == "zalo":
        try:
            sync_zalo_webhook(bot_id, base_url)
            return {"status": "ok", "message": "Zalo bot created and webhook configured"}
        except Exception as e:
            logger.error(f"Error creating Zalo bot: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to create Zalo bot: {str(e)}")
    elif platform == "whatapps":
        try:
            sync_zalo_webhook(bot_id, base_url)
            return {"status": "ok", "message": "WhatsApp bot created and webhook configured"}
        except Exception as e:
            logger.error(f"Error creating WhatsApp bot: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to create WhatsApp bot: {str(e)}")
    else:
        raise HTTPException(status_code=400, detail=f"Platform {platform} not supported yet")

@router.delete("/{botId}", response_model=GenericResponse, summary="Delete a bot")
async def delete_bot(botId: str = Path(..., description="The ID of the bot to delete")):
    """Removes a bot's configuration and stops any active listeners (for Telegram)."""
    bot_id = botId
    bot_config_data = redis_client.hgetall(f"bot_config:{bot_id}")
    if not bot_config_data:
        raise HTTPException(status_code=404, detail="Bot not found")

    platform = bot_config_data.get("platform")
    token = bot_config_data.get("token")

    if platform == "telegram" and token:
        delete_telegram_webhook(token)

    redis_client.delete(f"bot_config:{bot_id}")
    return {"status": "ok", "message": f"Bot {bot_id} deleted"}

@router.get("/{botId}/status", response_model=BotStatusResponse, summary="Get bot status")
async def get_bot_status(botId: str = Path(..., description="The ID of the bot to check")):
    """Checks if the bot's listener is active (for Telegram) or gets status from the external API (for Zalo)."""
    bot_id = botId
    bot_config_data = redis_client.hgetall(f"bot_config:{bot_id}")
    if not bot_config_data:
        raise HTTPException(status_code=404, detail="Bot not found")

    platform = bot_config_data.get("platform")
    token = bot_config_data.get("token")

    current_config = get_system_config()
    base_url = current_config.get("BASE_URL")

    logger.info(f"Current config {base_url}")
    if platform == "telegram":
        if not token:
            return {"status": "down", "platform": "telegram", "error": "No token configured"}

        webhook_info = get_telegram_webhook_info(token)
        if webhook_info.get("ok"):
            expected_url = f"{base_url}/api/hook?platform=telegram&bot_id={bot_id}"
            actual_url = webhook_info.get("result", {}).get("url")
            status = "up" if actual_url == expected_url else "down"
            return {
                "status": status,
                "platform": "telegram",
                "details": webhook_info.get("result")
            }
        return {"status": "down", "platform": "telegram", "error": webhook_info.get("error")}

    elif platform == "zalo":
        try:
            status_data = get_zalo_status(bot_id)
            status = "up" if status_data.get("isAuthenticated") else "down"
            return {"status": status, "platform": "zalo", "details": status_data}
        except Exception as e:
            return {"status": "down", "platform": "zalo", "error": str(e)}

    elif platform == "whatapps":
        try:
            status_data = get_zalo_status(bot_id)
            status = "up" if status_data.get("isAuthenticated") else "down"
            return {"status": status, "platform": "whatapps", "details": status_data}
        except Exception as e:
            return {"status": "down", "platform": "whatapps", "error": str(e)}

    return {"status": "unknown", "platform": platform}

@router.get("/{botId}/qrcode.png", summary="Get QR code for bot authentication")
async def get_bot_qrcode(botId: str = Path(..., description="The ID of the bot")):
    """
    Returns a PNG QR code for bot authentication. Currently only supported for Zalo.
    """
    bot_id = botId
    bot_config_data = redis_client.hgetall(f"bot_config:{bot_id}")
    if not bot_config_data:
        raise HTTPException(status_code=404, detail="Bot not found")

    platform = bot_config_data.get("platform")

    if platform in ["zalo", "whatapps"]:
        try:
            qr_content = get_zalo_qr_code(bot_id)
            return Response(content=qr_content, media_type="image/png")
        except Exception as e:
            logger.error(f"Error fetching QR code for platform {platform} for bot {bot_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to fetch QR code: {str(e)}")
    else:
        raise HTTPException(status_code=400, detail=f"QR code authentication not supported for platform {platform}")

@router.post("/{botId}/send", response_model=Dict[str, Any], summary="Send a message")
async def send_bot_message(
    botId: str = Path(..., description="The ID of the bot to send the message from"),
    request: SendMessageRequest = Body(...)
):
    """Sends a message through the specified bot using the appropriate platform provider."""
    bot_id = botId
    bot_config_data = redis_client.hgetall(f"bot_config:{bot_id}")
    if not bot_config_data:
        raise HTTPException(status_code=404, detail="Bot not found")

    platform_name = bot_config_data.get("platform").capitalize()

    send_data = {
        "bot_id": bot_id,
        "token": bot_config_data.get("token"),
        "content": request.content,
        "user_id": request.user_id,
        "group_id": request.group_id,
        "type": request.type,
        "message_id": request.message_id,
        "platform_name": platform_name,
    }

    try:
        send_message.apply_async(args=(send_data,), queue="celery_send_message")
        return {"status": "ok", "message": "Message queued for sending"}
    except Exception as e:
        logger.error(f"Error queuing message: {e}")
        raise HTTPException(status_code=500, detail=str(e))
