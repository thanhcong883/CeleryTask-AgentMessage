import security
import logging
from fastapi import APIRouter, HTTPException, Request, Query, Depends
from models import GenericResponse
from database import redis_client
from telegram_service import store_received_message
from tasks import process_message
from media_utils import (
    get_folder_structure,
    download_file_generic,
    download_telegram_file,
)
from api_client import create_strapi_folder, upload_to_strapi
import os
import uuid

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/hook", tags=["Webhooks"])


@router.post(
    "",
    response_model=GenericResponse,
    summary="Universal message hook",
    dependencies=[Depends(security.verify_hook_token)],
)
async def universal_hook(
    request: Request,
    platform: str = Query(
        "zalo", description="The platform type (zalo, telegram, whatsapp)"
    ),
    bot_id: str = Query(None, description="The bot ID (required for telegram)"),
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

        message_type = "text"
        media_urls = []
        msg_type_zalo = raw_data.get("msgType")
        if msg_type_zalo in ["share.file", "chat.photo", "chat.video", "chat.voice"]:
            content_data = raw_data.get("content", {})
            if isinstance(content_data, str):
                import json

                try:
                    content_data = json.loads(content_data)
                except Exception:
                    pass

            href = content_data.get("href") if isinstance(content_data, dict) else None

            if href:
                message_type = "media"
                folder_path = get_folder_structure("Zalo", conv_id)
                ext = (
                    content_data.get("params", {}).get("fileExt", "bin")
                    if isinstance(content_data, dict)
                    and isinstance(content_data.get("params"), dict)
                    else "bin"
                )
                # If params is a string (like in the payload), try parsing it
                if isinstance(content_data, dict) and isinstance(
                    content_data.get("params"), str
                ):
                    import json

                    try:
                        params_dict = json.loads(content_data.get("params"))
                        ext = params_dict.get("fileExt", "bin")
                    except Exception:
                        pass

                filename = f"{uuid.uuid4()}.{ext}"
                local_path = os.path.join("/tmp/downloads", folder_path, filename)

                if download_file_generic(href, local_path):
                    s3_key = f"{folder_path}/{filename}"
                    s3_url = upload_to_s3(local_path, s3_key)
                    if s3_url:
                        media_urls.append(s3_url)

        msg_data = {
            "platform_name": "Zalo",
            "message_type": message_type,
            "media_urls": media_urls,
            "content": content,
            "platform_user_id": sender_id,
            "platform_conv_id": conv_id,
            "token": token,
            "type": msg_type,
            "name": name,
            "account_id": received_bot_id,
            "platform_msg_id": message_id,
            "sender_time": sender_time,
            "title": title,
            "isSelf": body.get("isSelf"),
        }
    elif platform == "whatsapp":
        data_field = body.get("data") or {}
        if not isinstance(data_field, dict):
            data_field = {}

        received_bot_id = body.get("accountId")
        if not received_bot_id:
            received_bot_id = data_field.get("idTo")

        bot_config = redis_client.hgetall(f"bot_config:{received_bot_id}")
        token = bot_config.get("token") if bot_config else None

        raw_block = body.get("raw") or {}
        raw_data = raw_block.get("data", {}) if isinstance(raw_block, dict) else {}
        if not isinstance(raw_data, dict):
            raw_data = {}

        is_group = bool(body.get("isGroup") or data_field.get("isGroup", False))
        msg_type = "group" if is_group else "private"

        wa_msg = data_field.get("message")
        wa_msg = wa_msg if isinstance(wa_msg, dict) else {}

        ext_text = wa_msg.get("extendedTextMessage") or {}
        img = wa_msg.get("imageMessage") or {}
        vid = wa_msg.get("videoMessage") or {}
        content_text = (
            wa_msg.get("conversation")
            or ext_text.get("text")
            or img.get("caption")
            or vid.get("caption")
            or raw_data.get("content")
            or body.get("text")
            or data_field.get("text")
        )

        if is_group:
            sender_id = (
                data_field.get("participant")
                or raw_data.get("uidFrom")
                or body.get("from")
            )
            conv_id = (
                body.get("threadId") or data_field.get("from") or raw_data.get("idTo")
            )
            title = data_field.get("group_name") or body.get("title") or "unknown"
            name = (
                data_field.get("user_name")
                or raw_data.get("dName")
                or sender_id
                or "unknown"
            )
        else:
            sender_id = (
                data_field.get("from") or raw_data.get("uidFrom") or body.get("from")
            )
            conv_id = (
                body.get("threadId")
                or data_field.get("from")
                or raw_data.get("idTo")
                or sender_id
            )
            title = body.get("title") or data_field.get("user_name") or "unknown"
            name = (
                data_field.get("user_name")
                or raw_data.get("dName")
                or sender_id
                or "unknown"
            )

        message_id = data_field.get("message_id") or raw_data.get("msgId")
        sender_time = (
            body.get("time") or data_field.get("time") or data_field.get("timestamp")
        )

        message_type = "text"
        media_urls = []
        wa_msg = data_field.get("message")
        wa_msg = wa_msg if isinstance(wa_msg, dict) else {}

        media_url = None
        ext = "bin"
        if "documentMessage" in wa_msg:
            media_url = wa_msg["documentMessage"].get("url")
            ext = wa_msg["documentMessage"].get("fileName", "doc").split(".")[-1]
        elif "imageMessage" in wa_msg:
            media_url = wa_msg["imageMessage"].get("url")
            ext = "jpg"
        elif "videoMessage" in wa_msg:
            media_url = wa_msg["videoMessage"].get("url")
            ext = "mp4"

        if media_url:
            message_type = "media"
            folder_path = get_folder_structure("Whatsapp", conv_id)
            filename = f"{uuid.uuid4()}.{ext}"
            local_path = os.path.join("/tmp/downloads", folder_path, filename)

            if download_file_generic(media_url, local_path):
                s3_key = f"{folder_path}/{filename}"
                s3_url = upload_to_s3(local_path, s3_key)
                if s3_url:
                    media_urls.append(s3_url)

        msg_data = {
            "platform_name": "Whatsapp",
            "message_type": message_type,
            "media_urls": media_urls,
            "content": content_text,
            "platform_user_id": sender_id,
            "platform_conv_id": conv_id,
            "token": token,
            "type": msg_type,
            "name": name,
            "account_id": received_bot_id,
            "platform_msg_id": message_id,
            "sender_time": sender_time,
            "title": title,
            "isSelf": body.get("isSelf"),
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
        if not message or (
            "text" not in message
            and "photo" not in message
            and "document" not in message
            and "video" not in message
            and "voice" not in message
        ):
            return {"status": "ok", "message": "No text message to process"}

        chat = message.get("chat", {})
        from_user = message.get("from", {})
        msg_type = "private" if chat.get("type") == "private" else "group"
        message_id = message.get("message_id")
        sender_time = message.get("date")
        # todo: if first_name or last_name is None use username
        name = from_user.get("first_name") or from_user.get("username") + " " + (
            from_user.get("last_name") or ""
        )

        title = chat.get("title")

        message_type = "text"
        media_urls = []
        file_id = None
        ext = "bin"

        if "photo" in message and message["photo"]:
            # Get largest photo
            file_id = message["photo"][-1]["file_id"]
            ext = "jpg"
        elif "document" in message:
            file_id = message["document"]["file_id"]
            ext = message["document"].get("file_name", "doc").split(".")[-1]
        elif "video" in message:
            file_id = message["video"]["file_id"]
            ext = "mp4"
        elif "voice" in message:
            file_id = message["voice"]["file_id"]
            ext = "ogg"

        if file_id and token:
            message_type = "media"
            folder_path = get_folder_structure("Telegram", str(chat.get("id")))
            filename = f"{uuid.uuid4()}.{ext}"
            local_path = os.path.join("/tmp/downloads", folder_path, filename)

            if download_telegram_file(file_id, token, local_path):
                s3_key = f"{folder_path}/{filename}"
                s3_url = upload_to_s3(local_path, s3_key)
                if s3_url:
                    media_urls.append(s3_url)

        msg_data = {
            "platform_name": "Telegram",
            "message_type": message_type,
            "media_urls": media_urls,
            "content": message.get("text", message.get("caption", "")),
            "platform_user_id": str(from_user.get("id")),
            "platform_conv_id": str(chat.get("id")),
            "token": token,
            "type": msg_type,
            "account_id": bot_id,
            "platform_msg_id": message_id,
            "name": name,
            "title": title,
            "sender_time": sender_time,
        }
    else:
        raise HTTPException(
            status_code=400, detail=f"Platform {platform} not supported on this hook"
        )

    store_received_message(msg_data)
    process_message.delay(msg_data)
    return {"status": "ok"}
