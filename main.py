import logging
from fastapi import FastAPI
import config
from database import redis_client
from zalo_service import sync_zalo_webhook
from telegram_service import sync_telegram_webhook
from bot_routes import router as bot_router
from webhook_routes import router as webhook_router
from message_routes import router as message_router

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global configuration that can be updated for testing
CONFIG = {
    "BASE_URL": config.BASE_URL
}

# --- Application Initialization ---

app = FastAPI(
    title="Bot Management System API",
    description="API for managing Telegram and Zalo bots, including message listening and sending.",
    version="1.0.0",
)

# Include Routers
app.include_router(bot_router)
app.include_router(webhook_router)
app.include_router(message_router)

def sync_all_bots():
    """Syncs webhook configuration for all bots in Redis."""
    logger.info("Syncing all bots...")
    try:
        keys = redis_client.keys("bot_config:*")
        for key in keys:
            try:
                bot_data = redis_client.hgetall(key)
                bot_id = key.split(":")[-1]
                platform = bot_data.get("platform")
                token = bot_data.get("token")

                if platform == "telegram":
                    if token:
                        logger.info(f"Syncing Telegram bot {bot_id} webhook")
                        sync_telegram_webhook(bot_id, token, CONFIG['BASE_URL'])
                elif platform in ["zalo", "whatapps"]:
                    logger.info(f"Syncing {platform} webhook for {bot_id}")
                    sync_zalo_webhook(bot_id, CONFIG['BASE_URL'])
            except Exception as bot_err:
                logger.error(f"Error syncing bot {key}: {bot_err}")

    except Exception as e:
        logger.error(f"Error during bot sync: {e}")

@app.on_event("startup")
async def startup_event():
    """Initializes existing bot configurations from Redis on startup."""
    logger.info("Service starting up...")
    # Clear all Telegram running locks as they are no longer used
    running_locks = redis_client.keys("bot_running:*")
    if running_locks:
        logger.info(f"Clearing {len(running_locks)} stale Telegram bot locks")
        redis_client.delete(*running_locks)

    sync_all_bots()

@app.get("/", tags=["General"])
async def root():
    return {"status": "ok", "message": "Bot Management System API is running"}

@app.get("/config", tags=["General"])
async def get_config():
    """Returns the current runtime configuration."""
    return {"status": "ok", "config": CONFIG}

@app.post("/api/config", tags=["System"])
async def update_runtime_config(new_config: dict):
    """Updates the runtime configuration (e.g., BASE_URL) and re-syncs all bots."""
    CONFIG.update(new_config)
    sync_all_bots()
    return {"status": "ok", "config": CONFIG}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
