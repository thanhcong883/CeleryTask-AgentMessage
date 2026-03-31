import security
import logging
from fastapi import FastAPI, Depends, Request, HTTPException, status, Form
from fastapi.responses import StreamingResponse, HTMLResponse, RedirectResponse
import config
import httpx
import base64
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

@app.get("/login", response_class=HTMLResponse)
async def login_get():
    return """
    <html>
        <head>
            <title>Flower Login</title>
            <style>
                body { font-family: Arial, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; background-color: #f0f2f5; margin: 0; }
                form { background: white; padding: 2rem; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); width: 300px; }
                h2 { margin-top: 0; text-align: center; color: #333; }
                input { display: block; width: 100%; padding: 0.75rem; margin: 1rem 0; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; }
                button { width: 100%; padding: 0.75rem; background-color: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 1rem; }
                button:hover { background-color: #0056b3; }
                .error { color: red; text-align: center; margin-bottom: 1rem; }
            </style>
        </head>
        <body>
            <form method="post">
                <h2>Flower Login</h2>
                <input type="text" name="username" placeholder="Username" required>
                <input type="password" name="password" placeholder="Password" required>
                <button type="submit">Login</button>
            </form>
        </body>
    </html>
    """

@app.post("/login")
async def login_post(username: str = Form(...), password: str = Form(...)):
    if username == config.FLOWER_USER and password == config.FLOWER_PASSWORD:
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        auth_str = f"{username}:{password}"
        auth_bytes = auth_str.encode("ascii")
        base64_auth = base64.b64encode(auth_bytes).decode("ascii")
        response.set_cookie(key="flower_auth", value=base64_auth, httponly=True)
        return response
    else:
        return HTMLResponse(content="""
        <html>
            <head>
                <title>Flower Login</title>
                <style>
                    body { font-family: Arial, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; background-color: #f0f2f5; margin: 0; }
                    form { background: white; padding: 2rem; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); width: 300px; }
                    h2 { margin-top: 0; text-align: center; color: #333; }
                    input { display: block; width: 100%; padding: 0.75rem; margin: 1rem 0; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; }
                    button { width: 100%; padding: 0.75rem; background-color: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 1rem; }
                    button:hover { background-color: #0056b3; }
                    .error { color: red; text-align: center; margin-bottom: 1rem; font-size: 0.9rem; }
                </style>
            </head>
            <body>
                <form method="post">
                    <h2>Flower Login</h2>
                    <div class="error">Invalid username or password</div>
                    <input type="text" name="username" placeholder="Username" required>
                    <input type="password" name="password" placeholder="Password" required>
                    <button type="submit">Login</button>
                </form>
            </body>
        </html>
        """, status_code=401)

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login")
    response.delete_cookie("flower_auth")
    return response

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception handler caught: {exc}", exc_info=True)
    return HTMLResponse(
        status_code=500,
        content="""
        <html>
            <head>
                <title>500 Internal Server Error</title>
                <style>
                    body { font-family: Arial, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; background-color: #f0f2f5; margin: 0; }
                    .container { background: white; padding: 2rem; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center; max-width: 500px; }
                    h1 { color: #dc3545; }
                    p { color: #6c757d; }
                    a { color: #007bff; text-decoration: none; }
                    a:hover { text-decoration: underline; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>500 Internal Server Error</h1>
                    <p>Oops! Something went wrong on our end.</p>
                    <p>Please try again later or contact support if the issue persists.</p>
                    <a href="/">Go to Home</a>
                </div>
            </body>
        </html>
        """
    )

# Catch-all proxy for Flower
@app.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
async def flower_proxy(request: Request, path_name: str):
    """Proxies all remaining requests to Flower with authentication."""
    # Retrieve the auth token from the cookie
    flower_auth = request.cookies.get("flower_auth")

    # If no auth token, redirect to login page (except for static assets or if it's already the login page)
    # Actually, because of the catch-all, we need to be careful.
    # The /login route is defined above, so FastAPI should match it first.
    if not flower_auth:
        return RedirectResponse(url="/login")

    url = httpx.URL(config.FLOWER_URL).join(request.url.path)
    # if request.query_params:
    #     url = url.copy_with(query=str(request.query_params).encode())

    async with httpx.AsyncClient() as client:
        # Prepare request
        content = await request.body()
        headers = dict(request.headers)
        # Remove host header as it will be set by httpx
        headers.pop("host", None)
        headers.pop("content-length", None)

        # Inject the Authorization header for Flower
        headers["Authorization"] = f"Basic {flower_auth}"

        proxy_req = client.build_request(
            method=request.method,
            url=url,
            params=request.query_params,
            content=content,
            headers=headers,
            timeout=None
        )

        try:
            response = await client.send(proxy_req, stream=True)
        except Exception as e:
            logger.error(f"Error proxying to Flower: {e}")
            # Raise exception instead of return to trigger the global exception handler
            raise e

        # Filter out problematic headers
        excluded_headers = ["content-length", "transfer-encoding", "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "upgrade"]
        response_headers = {
            k: v for k, v in response.headers.items()
            if k.lower() not in excluded_headers
        }

        return StreamingResponse(
            response.aiter_bytes(),
            status_code=response.status_code,
            headers=response_headers,
            background=None
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
