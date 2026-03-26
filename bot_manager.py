import asyncio
import logging
import json
from typing import Dict, Any, Optional
import redis
import httpx
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

import config
from tasks import process_message

logger = logging.getLogger(__name__)

class BotManager:
    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url, decode_responses=True)
        self.telegram_apps: Dict[str, Any] = {}
        self.zalo_system_url = config.ZALO_SYSTEM_URL

    async def _telegram_message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return

        # Get bot token to find botId
        bot_token = context.application.bot.token
        # Find botId in redis (we should store mapping token -> botId or just use a lookup)
        # For simplicity, we'll store bot config in redis

        # We need the botId to get the full config
        # We can store botId in context.bot_data if we set it up
        bot_id = context.bot_data.get("botId")
        if not bot_id:
            logger.error("botId not found in bot_data")
            return

        bot_config_raw = self.redis.get(f"bot_configs:{bot_id}")
        if not bot_config_raw:
            logger.error(f"Config not found for bot {bot_id}")
            return

        bot_config = json.loads(bot_config_raw)

        payload = {
            "sender_type": "customer",
            "sender_id": str(update.message.from_user.id),
            "platform_msg_id": str(update.message.message_id),
            "content": update.message.text or "",
            "sender_time": str(int(update.message.date.timestamp())),
            "platform_id": bot_config.get("platform_id", "2"), # Default Telegram
            "account_id": bot_id,
            "type": update.message.chat.type,
            "name": update.message.from_user.full_name,
            "title": update.message.chat.title or update.message.from_user.full_name,
            "platform_user_id": str(update.message.from_user.id),
            "platform_conv_id": str(update.message.chat_id),
            "role": None,
            "token": bot_token,
            "platform_name": "Telegram"
        }

        logger.info(f"Forwarding Telegram message from {bot_id} to celery")
        process_message.delay(payload)

    async def start_bot(self, bot_id: str, platform: str, token: Optional[str], platform_id: Optional[str] = None):
        config_data = {
            "platform": platform,
            "token": token,
            "platform_id": platform_id or ("1" if platform == "zalo" else "2")
        }
        self.redis.set(f"bot_configs:{bot_id}", json.dumps(config_data))

        if platform == "telegram":
            if not token:
                raise ValueError("Token is required for Telegram bot")

            if bot_id in self.telegram_apps:
                await self.stop_bot(bot_id)

            app = ApplicationBuilder().token(token).build()
            app.bot_data["botId"] = bot_id
            app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self._telegram_message_handler))

            await app.initialize()
            await app.start()
            # Start polling in background
            task = asyncio.create_task(app.updater.start_polling())
            self.telegram_apps[bot_id] = {"app": app, "task": task}
            logger.info(f"Started Telegram bot {bot_id}")

        elif platform == "zalo":
            async with httpx.AsyncClient() as client:
                # Create account
                resp = await client.post(f"{self.zalo_system_url}/api/accounts", json={"accountId": bot_id})
                resp.raise_for_status()

                # Configure webhook
                webhook_url = f"{config.WEBHOOK_BASE_URL}/api/hook?platform=zalo&botId={bot_id}"
                resp = await client.post(f"{self.zalo_system_url}/api/{bot_id}/webhook-config", json={"webhookUrl": webhook_url})
                resp.raise_for_status()
                logger.info(f"Configured Zalo bot {bot_id} with webhook {webhook_url}")

    async def stop_bot(self, bot_id: str):
        bot_config_raw = self.redis.get(f"bot_configs:{bot_id}")
        if not bot_config_raw:
            return

        bot_config = json.loads(bot_config_raw)
        platform = bot_config.get("platform")

        if platform == "telegram":
            if bot_id in self.telegram_apps:
                entry = self.telegram_apps.pop(bot_id)
                app = entry["app"]
                task = entry["task"]
                task.cancel()
                await app.updater.stop()
                await app.stop()
                await app.shutdown()
                logger.info(f"Stopped Telegram bot {bot_id}")

        elif platform == "zalo":
            async with httpx.AsyncClient() as client:
                await client.delete(f"{self.zalo_system_url}/api/{bot_id}")
                logger.info(f"Deleted Zalo bot {bot_id} from system")

        self.redis.delete(f"bot_configs:{bot_id}")

    async def get_bot_status(self, bot_id: str) -> str:
        bot_config_raw = self.redis.get(f"bot_configs:{bot_id}")
        if not bot_config_raw:
            return "not_found"

        bot_config = json.loads(bot_config_raw)
        platform = bot_config.get("platform")

        if platform == "telegram":
            return "up" if bot_id in self.telegram_apps else "down"

        elif platform == "zalo":
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"{self.zalo_system_url}/api/{bot_id}/auth-status")
                    if resp.status_code == 200:
                        data = resp.json()
                        return "up" if data.get("isAuthenticated") else "down"
            except Exception:
                return "error"

        return "unknown"

bot_manager = BotManager(config.REDIS_URL)
