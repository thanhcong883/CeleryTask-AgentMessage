import logging
import json
from fastapi import APIRouter, HTTPException
from database import redis_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/messages", tags=["Messages"])

@router.get("", summary="Get all received messages from Redis")
async def get_received_messages():
    """Retrieves all received messages currently stored in Redis (up to 10 mins old)."""
    try:
        keys = redis_client.keys("received_msg:*")
        messages = []
        for key in keys:
            msg_json = redis_client.get(key)
            if msg_json:
                messages.append(json.loads(msg_json))
        return {"status": "ok", "messages": messages}
    except Exception as e:
        logger.error(f"Failed to retrieve messages from Redis: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
