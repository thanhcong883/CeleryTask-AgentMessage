import asyncio
import logging
import threading
import uuid
import json
from typing import Dict, Any, Optional
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from database import redis_client
from tasks import process_message

logger = logging.getLogger(__name__)

# Active Telegram bots: bot_id -> {"loop": loop, "stop_event": stop_event}
telegram_bots: Dict[str, Dict[str, Any]] = {}

def store_received_message(data: Dict[str, Any]):
    """Stores the received message in Redis with a 10-minute expiration."""
    try:
        msg_id = str(uuid.uuid4())
        key = f"received_msg:{msg_id}"
        redis_client.setex(key, 600, json.dumps(data))
        logger.info(f"Stored message {msg_id} in Redis with 10min expiry")
    except Exception as e:
        logger.error(f"Failed to store message in Redis: {e}")

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
