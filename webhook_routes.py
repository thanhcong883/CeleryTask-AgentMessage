import security
import logging
from fastapi import APIRouter, HTTPException, Request, Query, Depends
from models import GenericResponse
from database import redis_client
from telegram_service import store_received_message
from tasks import process_message

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/hook", tags=["Webhooks"])

@router.post("", response_model=GenericResponse, summary="Universal message hook", dependencies=[Depends(security.verify_hook_token)])
async def universal_hook(
    request: Request,
    platform: str = Query("zalo", description="The platform type (zalo, telegram)"),
    bot_id: str = Query(None, description="The bot ID (required for telegram)")
):
    """
    Webhook endpoint to receive messages from various platforms.
    Messages are formatted and pushed to a Celery task for processing.
    """
    body = await request.json()
    logger.info(f"Received {platform} hook: {body}")

    if platform == "zalo":
        # {'accountId': 'bot_zalo_1', 'title':'Group 1', 'from': 'Nguyễn Hữu Kiên', 'time': 1774943749889, 'text': '12', 'isGroup': True, 
        # 'threadId': '8877215926323712114', 'isSelf': False, 
        # 'raw': {'type': 1, 'data': {'actionId': '12733771563290', 
        #           'msgId': '7676592750243', 'cliMsgId': '1774943749869', 'msgType': 'webchat', 
        #           'uidFrom': '6643573306424440690', 'idTo': '8877215926323712114', 
        #           'dName': 'Nguyễn Hữu Kiên', 'ts': '1774943749889', 'status': 1, 'content': '12', 'notify': '1', 'ttl': 0, 'userId': '0', 'uin': '0', 'topOut': '0', 'topOutTimeOut': '0', 'topOutImprTimeOut': '0', 'propertyExt': {'color': 0, 'size': 0, 'type': 0, 'subType': 0, 'ext': '{"shouldParseLinkOrContact":0}'}, 'paramsExt': {'countUnread': 1, 'containType': 0, 'platformType': 1}, 'cmd': 521, 'st': 3, 'at': 5, 'realMsgId': '0'}, 'threadId': '8877215926323712114', 'isSelf': False}}
        received_bot_id = body.get("accountId")
        if not received_bot_id:
            data_field = body.get("data", {})
            received_bot_id = data_field.get("idTo")

        bot_config = redis_client.hgetall(f"bot_config:{received_bot_id}")
        token = bot_config.get("token") if bot_config else None

        raw_data = body.get("raw", {}).get("data", {})
        is_group = body.get("isGroup", False)
        msg_type = "group" if is_group else "private"

        content = raw_data.get("content") or body.get("text")
        sender_id = raw_data.get("uidFrom") or body.get("from")
        name = raw_data.get("dName") or body.get("from")
        conv_id = body.get("threadId") or raw_data.get("idTo")
        message_id = raw_data.get("msgId")
        # sendter time is body time or now
        sender_time = body.get("time")
        title = body.get("title") or "unknown"

        msg_data = {
            "platform_name": "Zalo",
            "content": content,
            "platform_user_id": sender_id,
            "platform_conv_id": conv_id,
            "token": token,
            "type": msg_type,
            "name": name,
            "account_id": received_bot_id,
            "platform_msg_id": message_id,
            "sender_time": sender_time,
            "title": title
        }
    elif platform == "telegram":
        # {'update_id': 695761324, 'message': {'message_id': 77, 'from': {'id': 688310870, 'is_bot': False, 'first_name': 'Kiên', 'last_name': 'Hữu', 'username': 'Kiennh', 'language_code': 'en'}, 'chat': {'id': -5236384276, 'title': 'Kiên & agc', 'type': 'group', 'all_members_are_administrators': False, 'accepted_gift_types': {'unlimited_gifts': False, 'limited_gifts': False, 'unique_gifts': False, 'premium_subscription': False, 'gifts_from_channels': False}}, 'date': 1774945399, 'text': '1'}}
        if not bot_id:
             # Try to find bot_id if not provided in query (though we set it in sync)
             logger.warning("Telegram hook received without bot_id query parameter")

        bot_config = redis_client.hgetall(f"bot_config:{bot_id}")
        token = bot_config.get("token") if bot_config else None

        # Telegram Update parsing
        message = body.get("message") or body.get("edited_message")
        if not message or "text" not in message:
            return {"status": "ok", "message": "No text message to process"}

        chat = message.get("chat", {})
        from_user = message.get("from", {})
        msg_type = "private" if chat.get("type") == "private" else "group"
        message_id = message.get("message_id")
        sender_time = message.get("date")
        name = from_user.get("first_name") + " " + from_user.get("last_name")
        title = chat.get("title")

        msg_data = {
            "platform_name": "Telegram",
            "content": message.get("text"),
            "platform_user_id": str(from_user.get("id")),
            "platform_conv_id": str(chat.get("id")),
            "token": token,
            "type": msg_type,
            "account_id": bot_id,
            "platform_msg_id": message_id,
            "name": name,
            "title": title,
            "sender_time": sender_time
        }
    else:
         raise HTTPException(status_code=400, detail=f"Platform {platform} not supported on this hook")

    store_received_message(msg_data)
    process_message.delay(msg_data)
    return {"status": "ok"}
