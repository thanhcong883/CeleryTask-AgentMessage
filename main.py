import logging
from fastapi import FastAPI
import config
from database import redis_client
from zalo_service import sync_zalo_webhook
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

@app.on_event("startup")
async def startup_event():
    """Initializes existing bot configurations from Redis on startup."""
    logger.info("Service starting up...")
    try:
        # Sync for all Zalo bots
        keys = redis_client.keys("bot_config:*")
        for key in keys:
            bot_data = redis_client.hgetall(key)
            if bot_data.get("platform") == "zalo":
                bot_id = key.split(":")[-1]
                sync_zalo_webhook(bot_id, CONFIG['BASE_URL'])
    except Exception as e:
        logger.error(f"Error during startup sync: {e}")

@app.get("/", tags=["General"])
async def root():
    return {"status": "ok", "message": "Bot Management System API is running"}

@app.get("/config", tags=["General"])
async def get_config():
    """Returns the current runtime configuration."""
    return {"status": "ok", "config": CONFIG}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
