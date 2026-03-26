import asyncio
import logging
import threading
from typing import Dict, Any, Optional, Union, List

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Body, Path, Query
from pydantic import BaseModel, Field
import redis
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

import config
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
    process_message.delay(data)

async def run_telegram_bot(bot_id: str, token: str, stop_event: asyncio.Event):
    logger.info(f"Starting Telegram bot {bot_id} listener")
    try:
        application = ApplicationBuilder().token(token).build()
        application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), telegram_message_handler))

        await application.initialize()
        await application.start()
        await application.updater.start_polling()

        await stop_event.wait()

        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        logger.info(f"Stopped Telegram bot {bot_id} listener")
    except Exception as e:
        logger.error(f"Error in Telegram bot {bot_id}: {e}")
    finally:
        if bot_id in telegram_bots:
            del telegram_bots[bot_id]

def start_bot_thread(bot_id: str, token: str):
    def run_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        stop_event = asyncio.Event()
        telegram_bots[bot_id] = {"loop": loop, "stop_event": stop_event}
        try:
            loop.run_until_complete(run_telegram_bot(bot_id, token, stop_event))
        finally:
            loop.close()

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()

# --- Zalo Integration Helpers ---

def create_zalo_account(bot_id: str):
    url = f"{config.ZALO_EXTERNAL_API_BASE}/api/accounts"
    response = requests.post(url, json={"botId": bot_id}, timeout=10)
    response.raise_for_status()
    return response.json()

def config_zalo_webhook(bot_id: str):
    url = f"{config.ZALO_EXTERNAL_API_BASE}/api/{bot_id}/webhook-config"
    webhook_url = f"{config.BASE_URL}/api/hook?platform=zalo"
    response = requests.post(url, json={"webhookUrl": webhook_url}, timeout=10)
    response.raise_for_status()
    return response.json()

def get_zalo_status(bot_id: str):
    url = f"{config.ZALO_EXTERNAL_API_BASE}/api/{bot_id}/auth-status"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.json()

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
    except Exception as e:
        logger.error(f"Error during startup: {e}")

@app.post("/api/bots", response_model=GenericResponse, tags=["Bots"], summary="Create a new bot")
async def create_bot(request: CreateBotRequest):
    """
    Initialize a new bot on the specified platform.

    - **Telegram**: Starts a long-polling listener in a background thread.
    - **Zalo**: Creates an account on the external system and configures a webhook.
    """
    bot_id = str(request.botId)
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
            return {"status": "ok", "message": "Telegram bot listener already running"}

        start_bot_thread(bot_id, token)
        return {"status": "ok", "message": "Telegram bot listener started"}

    elif platform == "zalo":
        try:
            create_zalo_account(bot_id)
            config_zalo_webhook(bot_id)
            return {"status": "ok", "message": "Zalo bot created and webhook configured"}
        except Exception as e:
            logger.error(f"Error creating Zalo bot: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to create Zalo bot: {str(e)}")

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
        is_up = botId in telegram_bots
        return {"status": "up" if is_up else "down", "platform": "telegram"}

    elif platform == "zalo":
        try:
            status_data = get_zalo_status(botId)
            return {"status": status_data.get("status", "unknown"), "platform": "zalo", "details": status_data}
        except Exception as e:
            return {"status": "down", "platform": "zalo", "error": str(e)}

    return {"status": "unknown", "platform": platform}

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

    data_field = body.get("data", {})
    bot_id = data_field.get("idTo")
    bot_config = redis_client.hgetall(f"bot_config:{bot_id}")
    token = bot_config.get("token") if bot_config else None

    msg_data = {
        "platform_name": "Zalo",
        "content": data_field.get("content"),
        "platform_user_id": data_field.get("uidFrom"),
        "platform_conv_id": data_field.get("uidFrom"),
        "token": token,
        "type": "private",
    }

    process_message.delay(msg_data)
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
