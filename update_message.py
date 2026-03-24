import logging
from datetime import datetime
from dateutil import parser

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)



def format_datetime(time_val):
    if not time_val:
        return datetime.now().isoformat()
    try:
        timestamp = float(time_val)
        return datetime.fromtimestamp(timestamp).isoformat()
    except (ValueError, TypeError):
        try:
            return parser.parse(str(time_val)).isoformat()
        except Exception:
            return datetime.now().isoformat()


def update_message_platform(platform, data, result):
    logger.info(f"Formulating update payload for platform '{platform}'")
    update_payload = {"message_status": "sent"}

    mess_id = data.get("message_id")
    if mess_id:
        update_payload["message_id"] = mess_id

    if platform.title() == "Telegram":
        update_payload.update(
            {
                "platform_msg_id": str(result.get("result", {}).get("message_id")),
                "content": result.get("result", {}).get("text"),
                "datetime": format_datetime(result.get("result", {}).get("date")),
            }
        )
    elif platform.title() == "Zalo":
        update_payload.update(
            {
                "platform_msg_id": str(result.get("data", {}).get("message_id")),
                "content": data.get("content"),
                "datetime": format_datetime(data.get("sent_time")),
            }
        )

    return update_payload
