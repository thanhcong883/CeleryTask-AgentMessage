import logging
from fastapi import Request, HTTPException
import config

logger = logging.getLogger(__name__)

def verify_token(request: Request, expected_token: str):
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
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
    elif alt_auth_header and alt_auth_header.startswith("Bearer "):
        token = alt_auth_header[7:]
    elif secret_token_header:
        token = secret_token_header

    if not token or token != expected_token:
        logger.warning(f"Unauthorized access attempt to {request.url.path}")
        raise HTTPException(status_code=403, detail="Forbidden")
    return token

async def verify_secret_token(request: Request):
    return verify_token(request, config.SECRET_TOKEN)

async def verify_hook_token(request: Request):
    return verify_token(request, config.HOOK_TOKEN)
