import security
import logging
from fastapi import FastAPI, Depends, Request, HTTPException, status
from fastapi.responses import StreamingResponse
import config
import httpx
from database import redis_client, get_system_config, update_system_config, CONFIG_REDIS_KEY
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

# --- Application Initialization ---

app = FastAPI(
    title="Bot Management System API",
    description="API for managing Telegram and Zalo bots, including message listening and sending.",
    version="1.0.0",
)

# Include Routers
app.include_router(bot_router, dependencies=[Depends(security.verify_secret_token)])
app.include_router(webhook_router)
app.include_router(message_router, dependencies=[Depends(security.verify_secret_token)])

def sync_all_bots():
    """Syncs webhook configuration for all bots in Redis."""
    logger.info("Syncing all bots...")
    current_config = get_system_config()
    base_url = current_config.get("BASE_URL")

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
                        sync_telegram_webhook(bot_id, token, base_url)
                elif platform in ["zalo", "whatapps"]:
                    logger.info(f"Syncing {platform} webhook for {bot_id}")
                    sync_zalo_webhook(bot_id, base_url)
            except Exception as bot_err:
                logger.error(f"Error syncing bot {key}: {bot_err}")

    except Exception as e:
        logger.error(f"Error during bot sync: {e}")

@app.on_event("startup")
async def startup_event():
    """Initializes existing bot configurations from Redis on startup."""
    logger.info("Service starting up...")

    # Initialize system configuration in Redis if it doesn't exist
    if not redis_client.exists(CONFIG_REDIS_KEY):
        logger.info("Initializing system configuration in Redis")
        initial_config = {"BASE_URL": config.BASE_URL}
        update_system_config(initial_config)

    # Clear all Telegram running locks as they are no longer used
    running_locks = redis_client.keys("bot_running:*")
    if running_locks:
        logger.info(f"Clearing {len(running_locks)} stale Telegram bot locks")
        redis_client.delete(*running_locks)

    sync_all_bots()

@app.get("/api/config", tags=["General"], dependencies=[Depends(security.verify_secret_token)])
async def get_config():
    """Returns the current runtime configuration."""
    return {"status": "ok", "config": get_system_config()}

@app.post("/api/config", tags=["System"], dependencies=[Depends(security.verify_secret_token)])
async def update_runtime_config(new_config: dict):
    """Updates the runtime configuration (e.g., BASE_URL) and re-syncs all bots."""
    update_system_config(new_config)
    sync_all_bots()
    return {"status": "ok", "config": get_system_config()}

# Catch-all proxy for Flower
@app.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
async def flower_proxy(request: Request, path_name: str):
    """Proxies all remaining requests to Flower."""
    url = httpx.URL(config.FLOWER_URL).join(request.url.path)
    if request.query_params:
        url = url.copy_with(query=request.query_params.encode())

    async with httpx.AsyncClient() as client:
        # Prepare request
        content = await request.body()
        headers = dict(request.headers)
        # Remove host header as it will be set by httpx
        headers.pop("host", None)

        proxy_req = client.build_request(
            method=request.method,
            url=url,
            content=content,
            headers=headers,
            timeout=None
        )

        response = await client.send(proxy_req, stream=True)

        return StreamingResponse(
            response.aiter_raw(),
            status_code=response.status_code,
            headers=dict(response.headers),
            background=None
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
