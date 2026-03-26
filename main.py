import asyncio
import logging
import threading
import uuid
import json
from typing import Dict, Any, Optional, Union, List

import config
from api_client import (
    get_conversation_info,
)

# Global configuration that can be updated for testing
CONFIG = {
    "BASE_URL": config.BASE_URL
}

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Body, Path, Query, Response
from pydantic import BaseModel, Field
import redis
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, ExtBot

from tasks import process_message

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# --- Models for Documentation ---

class BotOptions(BaseModel):
    platform: str = Field(..., description="Platform type: telegram, zalo, or whatapps", examples=["telegram"])
    token: Optional[str] = Field(None, description="Access token for the platform (required for Telegram)", examples=["7123456789:ABCDefgh-IJKLmnopQRstuvwxYZ12345678"])

class CreateBotRequest(BaseModel):
    botId: Union[str, int] = Field(..., description="Unique ID for the bot", examples=["my_telegram_bot_1"])
    options: BotOptions

class SendMessageRequest(BaseModel):
    content: str = Field(..., description="Message content to send", examples=["Hello from the bot!"])
    user_id: Optional[str] = Field(None, description="Recipient user ID for private messages", examples=["123456789"])
    group_id: Optional[str] = Field(None, description="Recipient group ID for group messages", examples=["-987654321"])
    type: str = Field("private", description="Message type: private or group", examples=["private"])

class GenericResponse(BaseModel):
    status: str = Field(..., examples=["ok"])
    message: Optional[str] = Field(None, examples=["Operation successful"])

class BotStatusResponse(BaseModel):
    status: str = Field(..., description="Bot status: up, down, or other platform-specific status", examples=["up"])
    platform: str = Field(..., examples=["telegram"])
    details: Optional[Dict[str, Any]] = None

# --- Application Initialization ---

app = FastAPI(
    title="Bot Management System API",
    description="API for managing Telegram and Zalo bots, including message listening and sending.",
    version="1.0.0",
)

# Redis client
try:
    redis_client = redis.from_url(config.REDIS_URL, decode_responses=True)
    redis_client.ping()
except Exception as e:
    logger.error(f"Failed to connect to Redis at {config.REDIS_URL}: {e}")
    redis_client = redis.Redis(host="localhost", decode_responses=True)

# Active Telegram bots: bot_id -> {"loop": loop, "stop_event": stop_event}
telegram_bots: Dict[str, Dict[str, Any]] = {}

# --- Telegram Listener Logic ---

async def telegram_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    data = {
        "platform_name": "Telegram",
        "content": update.message.text,
        "platform_user_id": str(update.message.from_user.id),
        "platform_conv_id": str(update.message.chat_id),
        "token": context.bot.token,
        "type": "private" if update.message.chat.type == "private" else "group",
    }

    logger.info(f"Received Telegram message from {data['platform_user_id']}")
    store_received_message(data)
    process_message.delay(data)



async def run_telegram_bot(bot_id: str, token: str, stop_event: asyncio.Event):
    logger.info(f"Starting Telegram bot {bot_id} listener")
    try:
        application = ApplicationBuilder().token(token).build()

        async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
            logger.error(f"Error in Telegram bot {bot_id}: {context.error}")
            if bot_id in telegram_bots:
                telegram_bots[bot_id]["status"] = "down"
                telegram_bots[bot_id]["error"] = str(context.error)

        application.add_error_handler(error_handler)
        application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), telegram_message_handler))

        await application.initialize()
        await application.start()
        await application.updater.start_polling()

        if bot_id in telegram_bots:
            telegram_bots[bot_id]["status"] = "up"
            telegram_bots[bot_id]["error"] = None

        # Periodically reset status to "up" to check if errors persist via error_handler
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=30)
            except asyncio.TimeoutError:
                if bot_id in telegram_bots and telegram_bots[bot_id]["status"] == "down":
                    telegram_bots[bot_id]["status"] = "up"
                    telegram_bots[bot_id]["error"] = None

        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        logger.info(f"Stopped Telegram bot {bot_id} listener")
    except Exception as e:
        logger.error(f"Error in Telegram bot {bot_id}: {e}")
        if bot_id in telegram_bots:
            telegram_bots[bot_id]["status"] = "down"
            telegram_bots[bot_id]["error"] = str(e)
    finally:
        if bot_id in telegram_bots:
            if stop_event.is_set():
                del telegram_bots[bot_id]
            else:
                telegram_bots[bot_id]["status"] = "down"

def store_received_message(data: Dict[str, Any]):
    """Stores the received message in Redis with a 10-minute expiration."""
    try:
        msg_id = str(uuid.uuid4())
        key = f"received_msg:{msg_id}"
        redis_client.setex(key, 600, json.dumps(data))
        logger.info(f"Stored message {msg_id} in Redis with 10min expiry")
    except Exception as e:
        logger.error(f"Failed to store message in Redis: {e}")

def start_bot_thread(bot_id: str, token: str):
    def run_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        stop_event = asyncio.Event()
        telegram_bots[bot_id] = {"loop": loop, "stop_event": stop_event, "status": "wait", "error": None}
        try:
            loop.run_until_complete(run_telegram_bot(bot_id, token, stop_event))
        finally:
            loop.close()

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()

# --- Zalo Integration Helpers ---

def get_zalo_accounts():
    url = f"{config.ZALO_EXTERNAL_API_BASE}/api/accounts"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.json()

def create_zalo_account(bot_id: str):
    url = f"{config.ZALO_EXTERNAL_API_BASE}/api/accounts"
    response = requests.post(url, json={"accountId": bot_id}, timeout=10)
    response.raise_for_status()
    return response.json()

def config_zalo_webhook(bot_id: str):
    url = f"{config.ZALO_EXTERNAL_API_BASE}/api/{bot_id}/webhook-config"
    webhook_url = f"{CONFIG['BASE_URL']}/api/hook?platform=zalo"
    response = requests.post(url, json={"webhookUrl": webhook_url}, timeout=10)
    response.raise_for_status()
    return response.json()

def get_zalo_webhook_config(bot_id: str):
    url = f"{config.ZALO_EXTERNAL_API_BASE}/api/{bot_id}/webhook-config"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.json()

def sync_zalo_webhook(bot_id: str):
    """Checks if the Zalo account exists and webhook matches the current CONFIG['BASE_URL']."""
    current_webhook = f"{CONFIG['BASE_URL']}/api/hook?platform=zalo"
    try:
        # 1. Check if account exists
        accounts = get_zalo_accounts()
        if not any(acc.get("accountId") == bot_id for acc in accounts):
            logger.info(f"Creating Zalo account for {bot_id} on external platform")
            create_zalo_account(bot_id)
        
        # 2. Check and sync webhook config
        remote_config = get_zalo_webhook_config(bot_id)
        if remote_config.get("webhookUrl") != current_webhook:
            logger.info(f"Updating Zalo webhook for {bot_id} from {remote_config.get('webhookUrl')} to {current_webhook}")
            config_zalo_webhook(bot_id)
        else:
            logger.info(f"Zalo webhook for {bot_id} is already up to date.")
    except Exception as e:
        logger.error(f"Failed to sync Zalo webhook for {bot_id}: {e}")

def get_zalo_status(bot_id: str):
    url = f"{config.ZALO_EXTERNAL_API_BASE}/api/{bot_id}/auth-status"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.json()
def get_zalo_qr_code(bot_id: str):
    url = f"{config.ZALO_EXTERNAL_API_BASE}/qr/{bot_id}.png"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.content


# --- API Endpoints ---

@app.on_event("startup")
async def startup_event():
    """Restart active Telegram listeners on server startup."""
    try:
        bot_keys = redis_client.keys("bot_config:*")
        for key in bot_keys:
            bot_data = redis_client.hgetall(key)
            if bot_data.get("platform") == "telegram" and bot_data.get("token"):
                bot_id = key.split(":")[-1]
                start_bot_thread(bot_id, bot_data["token"])
                logger.info(f"Restarted Telegram listener for bot {bot_id}")
            elif bot_data.get("platform") == "zalo":
                bot_id = key.split(":")[-1]
                sync_zalo_webhook(bot_id)
                logger.info(f"Synced Zalo webhook for bot {bot_id} on startup")
    except Exception as e:
        logger.error(f"Error during startup: {e}")

@app.get("/api/bots", tags=["Bots"], summary="List all configured bots")
async def list_bots():
    """Retrieves a list of all bots currently stored in Redis with their platform and configuration."""
    try:
        keys = redis_client.keys("bot_config:*")
        bots = []
        for key in keys:
            bot_id = key.split(":")[-1]
            config = redis_client.hgetall(key)
            bots.append({
                "botId": bot_id,
                "platform": config.get("platform"),
                "token": config.get("token")
            })
        return {"status": "ok", "bots": bots}
    except Exception as e:
        logger.error(f"Failed to list bots from Redis: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.post("/api/config", tags=["System"])
async def update_system_config(payload: Dict[str, Any]):
    """Update system configuration at runtime (e.g., BASE_URL for tunnels)."""
    if "BASE_URL" in payload:
        CONFIG["BASE_URL"] = payload["BASE_URL"]
        logger.info(f"System BASE_URL updated to: {CONFIG['BASE_URL']}")
        # Trigger re-sync for all Zalo bots
        keys = redis_client.keys("bot_config:*")
        for key in keys:
            bot_data = redis_client.hgetall(key)
            if bot_data.get("platform") == "zalo":
                bot_id = key.split(":")[-1]
                sync_zalo_webhook(bot_id)
    return {"status": "ok", "config": CONFIG}

@app.post("/api/bots", tags=["Bots"], summary="Create a new bot")
async def create_bot(request: CreateBotRequest):
    """
    Initialize a new bot on the specified platform.

    - **Telegram**: Starts a long-polling listener in a background thread.
    - **Zalo**: Creates an account on the external system and configures a webhook.
    """
    bot_id = str(request.botId)
    bot_config = redis_client.hgetall(f"bot_config:{bot_id}")
    if bot_config:
        if bot_config.get("platform") == "zalo":
             sync_zalo_webhook(bot_id)
        return {"status": "ok", "message": f"Bot {bot_id} already exists"}

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
        if bot_id in telegram_bots:
            if telegram_bots[bot_id].get("status") == "down":
                del telegram_bots[bot_id]
            else:
                return {"status": "ok", "message": "Telegram bot listener already running"}

        start_bot_thread(bot_id, token)
        return {"status": "ok", "message": "Telegram bot listener started"}

    elif platform == "zalo":
        try:
            sync_zalo_webhook(bot_id)
            return {"status": "ok", "message": "Zalo bot created and webhook configured"}
        except Exception as e:
            logger.error(f"Error creating Zalo bot: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to create Zalo bot: {str(e)}")
    elif platform == "whatapps":
        try:
            sync_zalo_webhook(bot_id)
            return {"status": "ok", "message": "WhatsApp bot created and webhook configured"}
        except Exception as e:
            logger.error(f"Error creating WhatsApp bot: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to create WhatsApp bot: {str(e)}")


    else:
        raise HTTPException(status_code=400, detail=f"Platform {platform} not supported yet")

@app.delete("/api/bots/{botId}", response_model=GenericResponse, tags=["Bots"], summary="Delete a bot")
async def delete_bot(botId: str = Path(..., description="The ID of the bot to delete")):
    """Removes a bot's configuration and stops any active listeners (for Telegram)."""
    bot_config = redis_client.hgetall(f"bot_config:{botId}")
    if not bot_config:
        raise HTTPException(status_code=404, detail="Bot not found")

    platform = bot_config.get("platform")

    if platform == "telegram":
        bot_info = telegram_bots.get(botId)
        if bot_info:
            if not bot_info["loop"].is_closed():
                bot_info["loop"].call_soon_threadsafe(bot_info["stop_event"].set)

    redis_client.delete(f"bot_config:{botId}")
    return {"status": "ok", "message": f"Bot {botId} deleted"}

@app.get("/api/bots/{botId}/status", response_model=BotStatusResponse, tags=["Bots"], summary="Get bot status")
async def get_bot_status(botId: str = Path(..., description="The ID of the bot to check")):
    """Checks if the bot's listener is active (for Telegram) or gets status from the external API (for Zalo)."""
    bot_config = redis_client.hgetall(f"bot_config:{botId}")
    if not bot_config:
        raise HTTPException(status_code=404, detail="Bot not found")

    platform = bot_config.get("platform")

    if platform == "telegram":
        bot_info = telegram_bots.get(botId)
        if bot_info:
            details = (bot_info.get("details") or {}).copy()
            if "error" not in details:
                details["error"] = bot_info.get("error")
            return {
                "status": bot_info.get("status", "up"),
                "platform": "telegram",
                "details": details
            }
        return {"status": "down", "platform": "telegram"}

    elif platform == "zalo":
        try:
            status_data = get_zalo_status(botId)
            status = "up" if status_data.get("isAuthenticated") else "down"
            return {"status": status, "platform": "zalo", "details": status_data}
        except Exception as e:
            return {"status": "down", "platform": "zalo", "error": str(e)}

    elif platform == "whatapps":
        try:
            status_data = get_zalo_status(botId)
            status = "up" if status_data.get("isAuthenticated") else "down"
            return {"status": status, "platform": "whatapps", "details": status_data}
        except Exception as e:
            return {"status": "down", "platform": "whatapps", "error": str(e)}

    return {"status": "unknown", "platform": platform}
@app.get("/api/bots/{botId}/qrcode.png", tags=["Bots"], summary="Get QR code for bot authentication")
async def get_bot_qrcode(botId: str = Path(..., description="The ID of the bot")):
    """
    Returns a PNG QR code for bot authentication. Currently only supported for Zalo.
    """
    bot_config = redis_client.hgetall(f"bot_config:{botId}")
    if not bot_config:
        raise HTTPException(status_code=404, detail="Bot not found")

    platform = bot_config.get("platform")

    if platform in ["zalo", "whatapps"]:
        try:
            qr_content = get_zalo_qr_code(botId)
            return Response(content=qr_content, media_type="image/png")
        except Exception as e:
            logger.error(f"Error fetching QR code for platform {platform} for bot {botId}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to fetch QR code: {str(e)}")
    else:
        raise HTTPException(status_code=400, detail=f"QR code authentication not supported for platform {platform}")


@app.post("/api/bots/{botId}/send", response_model=Dict[str, Any], tags=["Bots"], summary="Send a message")
async def send_bot_message(
    botId: str = Path(..., description="The ID of the bot to send the message from"),
    request: SendMessageRequest = Body(...)
):
    """Sends a message through the specified bot using the appropriate platform provider."""
    bot_config = redis_client.hgetall(f"bot_config:{botId}")
    if not bot_config:
        raise HTTPException(status_code=404, detail="Bot not found")

    from provider import PROVIDERS

    platform_name = bot_config.get("platform").capitalize()
    if platform_name not in PROVIDERS:
         raise HTTPException(status_code=400, detail=f"No provider for {platform_name}")

    send_data = {
        "bot_id": botId,
        "token": bot_config.get("token"),
        "content": request.content,
        "user_id": request.user_id,
        "group_id": request.group_id,
        "type": request.type,
    }

    try:
        result = PROVIDERS[platform_name].send(send_data)
        return {"status": "ok", "result": result}
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/hook", response_model=GenericResponse, tags=["Webhooks"], summary="Zalo message hook")
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

@app.get("/api/messages", tags=["Messages"], summary="Get all received messages from Redis")
async def get_received_messages():
    """Retrieves all received messages currently stored in Redis (up to 10 mins old)."""
    try:
        keys = redis_client.keys("received_msg:*")
        messages = []
        for key in keys:
            msg_json = redis_client.get(key)
            if msg_json:
                messages.append(json.loads(msg_json))
        return {"status": "ok", "messages": messages}
    except Exception as e:
        logger.error(f"Failed to retrieve messages from Redis: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
