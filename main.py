import logging
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, BackgroundTasks, Query
from pydantic import BaseModel
from typing import Optional, Dict, Any

import config
from bot_manager import bot_manager
from tasks import send_message, process_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initial startup (e.g., re-start existing bots from redis)
    logger.info("Starting up FastAPI server")
    # For a real system, we'd iterate over bot configs and re-start Telegram listeners here
    yield
    logger.info("Shutting down FastAPI server")

app = FastAPI(lifespan=lifespan)

class BotOptions(BaseModel):
    platform: str
    token: Optional[str] = None
    platform_id: Optional[str] = None

class CreateBotRequest(BaseModel):
    botId: str
    options: BotOptions

@app.post("/api/bots")
async def create_bot(req: CreateBotRequest):
    logger.info(f"Creating bot {req.botId} for platform {req.options.platform}")
    await bot_manager.start_bot(
        bot_id=req.botId,
        platform=req.options.platform,
        token=req.options.token,
        platform_id=req.options.platform_id
    )
    return {"status": "success", "botId": req.botId}

@app.delete("/api/bots/{botId}")
async def delete_bot(botId: str):
    logger.info(f"Deleting bot {botId}")
    await bot_manager.stop_bot(botId)
    return {"status": "success", "botId": botId}

@app.get("/api/bots/{botId}/status")
async def bot_status(botId: str):
    status = await bot_manager.get_bot_status(botId)
    return {"status": status, "botId": botId}

@app.post("/api/bots/{botId}/send")
async def send_bot_message(botId: str, req: Dict[str, Any]):
    # Call celery send_message
    # Use config from redis
    bot_config_raw = bot_manager.redis.get(f"bot_configs:{botId}")
    if not bot_config_raw:
        return {"status": "error", "message": "Bot not found"}, 404

    bot_config = json.loads(bot_config_raw)

    data = {
        "type": req.get("type", "private"),
        "group_id": req.get("group_id"),
        "user_id": req.get("user_id"),
        "content": req.get("content"),
        "platform_name": bot_config.get("platform").capitalize(),
        "message_id": req.get("message_id"), # For update
        "token": bot_config.get("token")
    }

    send_message.delay(data)
    return {"status": "sent"}

@app.post("/api/hook")
async def webhook(request: Request, platform: str = Query(...), botId: str = Query(None)):
    body = await request.json()
    logger.info(f"Received hook for {platform}: {json.dumps(body)}")

    if platform == "zalo":
        # Structure as per prompt
        # body: { "type": 0, "data": { ... }, "threadId": "...", "isSelf": false }
        data = body.get("data", {})

        # We need token and platform_id for the bot
        bot_config_raw = None
        if botId:
            bot_config_raw = bot_manager.redis.get(f"bot_configs:{botId}")

        bot_config = json.loads(bot_config_raw) if bot_config_raw else {}

        payload = {
            "sender_type": "customer",
            "sender_id": data.get("uidFrom"),
            "platform_msg_id": data.get("msgId"),
            "content": data.get("content"),
            "sender_time": str(int(int(data.get("ts", 0))/1000)), # ts is likely ms
            "platform_id": bot_config.get("platform_id", "1"), # Default Zalo
            "account_id": botId,
            "type": "private" if not body.get("isGroup") else "group", # Defaulting based on prompt
            "name": data.get("dName"),
            "title": data.get("dName"),
            "platform_user_id": data.get("uidFrom"),
            "platform_conv_id": body.get("threadId"),
            "role": None,
            "token": bot_config.get("token", ""),
            "platform_name": "Zalo"
        }

        process_message.delay(payload)
        return {"status": "processed"}

    return {"status": "ignored"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
