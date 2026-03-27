"""
Utilities for updating message details and formatting datetimes across platforms.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional
from dateutil import parser

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def format_datetime(time_val: Any) -> str:
    """
    Parse and format a datetime value to an ISO 8601 string.

    Tries converting to float (timestamp) first, then falls back to dateutil.parser.
    If both fail, or if value is empty, returns the current ISO timestamp.

    Args:
        time_val: A timestamp (float/int), ISO string, or any parseable date format.

    Returns:
        An ISO formatted datetime string.
    """
    if not time_val:
        return datetime.now().isoformat()

    try:
        timestamp: float = float(time_val)
        return datetime.fromtimestamp(timestamp).isoformat()
    except (ValueError, TypeError):
        try:
            return parser.parse(str(time_val)).isoformat()
        except Exception as e:
            logger.warning(
                "Failed to parse datetime value: %s, error: %s. Using current time.",
                time_val,
                e,
            )
            return datetime.now().isoformat()


def update_message_platform(
    platform: str, data: Dict[str, Any], result: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Formulate the update payload for a specific messaging platform.

    Extracts the relevant message ID, content, and datetime based on the
    platform's specific response structure (e.g., Telegram vs Zalo).

    Args:
        platform: The name of the platform ("Telegram", "Zalo", etc.).
        data: The original data payload sent to the platform.
        result: The API response payload returned by the platform.

    Returns:
        A dictionary containing updated payload fields (message_status,
        message_id, platform_msg_id, content, datetime).
    """
    logger.info("Formulating update payload for platform '%s'", platform)
    update_payload: Dict[str, Any] = {"message_status": "sent"}

    mess_id: Optional[str] = data.get("message_id")
    if mess_id:
        update_payload["message_id"] = mess_id

    platform_title: str = platform.title()

    if platform_title == "Telegram":
        telegram_result: Dict[str, Any] = result.get("result", {})
        update_payload.update(
            {
                "platform_msg_id": str(telegram_result.get("message_id", "")),
                "content": telegram_result.get("text", ""),
                "datetime": format_datetime(telegram_result.get("date")),
            }
        )
    elif platform_title == "Zalo":
        zalo_data: Dict[str, Any] = result.get("data", {})
        update_payload.update(
            {
                "platform_msg_id": str(zalo_data.get("message_id", "")),
                "content": data.get("content", ""),
                "datetime": format_datetime(data.get("sent_time")),
            }
        )
    else:
        logger.warning("Unsupported platform '%s'. Returning base payload.", platform)

    return update_payload
