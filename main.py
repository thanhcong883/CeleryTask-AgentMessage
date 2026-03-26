import asyncio
import logging
import threading
from typing import Dict, Any, Optional, Union

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel
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

app = FastAPI(title="Bot Management System")

# Redis client
try:
    redis_client = redis.from_url(config.REDIS_URL, decode_responses=True)
    redis_client.ping()
except Exception as e:
    logger.error(f"Failed to connect to Redis at {config.REDIS_URL}: {e}")
    redis_client = redis.Redis(host="localhost", decode_responses=True)

# Active Telegram bots: bot_id -> {"loop": loop, "stop_event": stop_event}
telegram_bots: Dict[str, Dict[str, Any]] = {}

class BotOptions(BaseModel):
    platform: str
    token: Optional[str] = None

class CreateBotRequest(BaseModel):
    botId: Union[str, int]
    options: BotOptions

class SendMessageRequest(BaseModel):
    content: str
    user_id: Optional[str] = None
    group_id: Optional[str] = None
    type: str = "private"

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

@app.post("/api/bots")
async def create_bot(request: CreateBotRequest):
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

@app.delete("/api/bots/{botId}")
async def delete_bot(botId: str):
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

@app.get("/api/bots/{botId}/status")
async def get_bot_status(botId: str):
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

@app.post("/api/bots/{botId}/send")
async def send_bot_message(botId: str, request: SendMessageRequest):
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

@app.post("/api/hook")
async def zalo_hook(request: Request, platform: str = "zalo"):
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
