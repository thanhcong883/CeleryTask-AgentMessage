import logging
from fastapi import Request, HTTPException
import config

logger = logging.getLogger(__name__)

async def verify_token(request: Request, expected_token: str):
    """
    Verifies the presence and validity of a token in the request headers.
    Checks 'Authorization: Bearer {token}', 'Authentication: Bearer {token}'
    and 'X-Telegram-Bot-Api-Secret-Token: {token}'.
    """
    auth_header = request.headers.get("Authorization")
    # Support literal 'Authentication' header as requested
    alt_auth_header = request.headers.get("Authentication")
    secret_token_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")

    token = None
    if auth_header:
        token = auth_header[7:] if auth_header.startswith("Bearer ") else auth_header
    elif alt_auth_header:
        token = alt_auth_header[7:] if alt_auth_header.startswith("Bearer ") else alt_auth_header
    elif secret_token_header:
        token = secret_token_header
    elif request.headers.get("X-Secret-Token"):
        token = request.headers.get("X-Secret-Token")
    elif request.headers.get("X-Webhook-Secret"):
        token = request.headers.get("X-Webhook-Secret")
    elif request.headers.get("Secret-Token"):
        token = request.headers.get("Secret-Token")
        
    if not token and request.query_params.get("token"):
        token = request.query_params.get("token")
    if not token and request.query_params.get("secretToken"):
        token = request.query_params.get("secretToken")
    if not token and request.query_params.get("secret_token"):
        token = request.query_params.get("secret_token")
        
    if not token and request.method in ["POST", "PUT"]:
        try:
            body = await request.json()
            if isinstance(body, dict):
                token = body.get("secretToken") or body.get("secret_token") or body.get("token")
        except Exception:
            pass

    if not token or token != expected_token:
        logger.warning(f"Unauthorized access attempt to {request.url.path}. Headers: {request.headers}")
        raise HTTPException(status_code=403, detail="Forbidden")
    return token

async def verify_secret_token(request: Request):
    return await verify_token(request, config.SECRET_TOKEN)

async def verify_hook_token(request: Request):
    return await verify_token(request, config.HOOK_TOKEN)
