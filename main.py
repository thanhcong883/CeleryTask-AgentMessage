import security
import logging
from fastapi import FastAPI, Depends, Request, HTTPException, status, Form
from fastapi.responses import StreamingResponse, HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
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

# Add SessionMiddleware for authentication cookie
app.add_middleware(SessionMiddleware, secret_key=config.SESSION_SECRET_KEY)

def is_authenticated(request: Request) -> bool:
    """Checks if the user session is authenticated."""
    auth_status = request.session.get("authenticated")
    logger.info(f"Checking authentication for {request.url.path}: {auth_status}")
    return auth_status is True

async def flower_proxy_request(request: Request, path: str):
    """Internal helper to proxy requests to Flower."""
    url = httpx.URL(config.FLOWER_URL).join(path)
    if request.query_params:
        url = url.copy_with(query=request.query_params.encode())

    logger.info(f"Proxying to Flower: {url}")
    async with httpx.AsyncClient() as client:
        content = await request.body()
        headers = dict(request.headers)
        headers.pop("host", None)
        headers.pop("authorization", None)

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

    if not redis_client.exists(CONFIG_REDIS_KEY):
        logger.info("Initializing system configuration in Redis")
        initial_config = {"BASE_URL": config.BASE_URL}
        update_system_config(initial_config)

    running_locks = redis_client.keys("bot_running:*")
    if running_locks:
        logger.info(f"Clearing {len(running_locks)} stale Telegram bot locks")
        redis_client.delete(*running_locks)

    sync_all_bots()

@app.get("/config", tags=["General"], dependencies=[Depends(security.verify_secret_token)])
async def get_config():
    """Returns the current runtime configuration."""
    return {"status": "ok", "config": get_system_config()}

@app.post("/api/config", tags=["System"], dependencies=[Depends(security.verify_secret_token)])
async def update_runtime_config(new_config: dict):
    """Updates the runtime configuration (e.g., BASE_URL) and re-syncs all bots."""
    update_system_config(new_config)
    sync_all_bots()
    return {"status": "ok", "config": get_system_config()}

def get_login_page(error: str = None):
    error_html = f'<p style="color: red;">{error}</p>' if error else ""
    return HTMLResponse(content=f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Login - Bot Management System</title>
        <style>
            body {{ font-family: Arial, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background-color: #f0f2f5; }}
            .login-container {{ background: white; padding: 2rem; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); width: 300px; }}
            h2 {{ text-align: center; margin-bottom: 1.5rem; }}
            input {{ width: 100%; padding: 10px; margin: 8px 0; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }}
            button {{ width: 100%; padding: 10px; background-color: #1877f2; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; }}
            button:hover {{ background-color: #166fe5; }}
        </style>
    </head>
    <body>
        <div class="login-container">
            <h2>Login</h2>
            {error_html}
            <form method="post" action="/login">
                <input type="text" name="username" placeholder="Username" required>
                <input type="password" name="password" placeholder="Password" required>
                <button type="submit">Log In</button>
            </form>
        </div>
    </body>
    </html>
    """)

@app.get("/")
async def root(request: Request):
    """Serves the login page or proxies root to Flower."""
    if is_authenticated(request):
        return await flower_proxy_request(request, "/")
    return get_login_page()

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    """Handles login and sets authentication session."""
    if username == config.FLOWER_USER and password == config.FLOWER_PASSWORD:
        logger.info(f"Successful login for {username}")
        request.session["authenticated"] = True
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    logger.warning(f"Failed login attempt for {username}")
    return get_login_page(error="Invalid username or password")

@app.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
async def flower_proxy(request: Request, path_name: str):
    """Proxies all remaining requests to Flower if authenticated."""
    if is_authenticated(request):
        return await flower_proxy_request(request, request.url.path)

    logger.info(f"Redirecting unauthenticated request for {path_name} to /")
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
