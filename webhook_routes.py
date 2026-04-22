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
    upload_to_s3,
    build_media_filename,
)

import os
import uuid
from typing import Optional

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

        # raw_data.content can be a dict for media messages (chat.photo,
        # share.file, ...). Only treat it as `content` when it is already a
        # string (plain text messages); for media we start with "" and let
        # the media block below set it from description/title if present.
        _raw_content = raw_data.get("content")
        if isinstance(_raw_content, str):
            content = _raw_content
        elif isinstance(body.get("text"), str) and not isinstance(
            _raw_content, dict
        ):
            content = body.get("text")
        else:
            content = ""
        sender_id = raw_data.get("uidFrom") or body.get("from")
        name = raw_data.get("dName") or body.get("from")
        conv_id = body.get("threadId") or raw_data.get("idTo")
        message_id = raw_data.get("msgId")
        # sendter time is body time or now
        sender_time = body.get("time")
        title = body.get("title") or "unknown"

        message_type = "text"
        media_url: Optional[str] = None
        msg_type_zalo = raw_data.get("msgType")
        if msg_type_zalo in ["share.file", "chat.photo", "chat.video", "chat.voice"]:
            import json
            from urllib.parse import urlparse

            content_data = raw_data.get("content", {})
            if isinstance(content_data, str):
                try:
                    content_data = json.loads(content_data)
                except Exception:
                    pass

            params_dict = {}
            if isinstance(content_data, dict):
                raw_params = content_data.get("params")
                if isinstance(raw_params, dict):
                    params_dict = raw_params
                elif isinstance(raw_params, str):
                    try:
                        params_dict = json.loads(raw_params)
                    except Exception:
                        params_dict = {}

            # Prefer HD URL for photo/video, fallback to href
            download_url = None
            if isinstance(content_data, dict):
                download_url = (
                    params_dict.get("hd")
                    or content_data.get("href")
                    or content_data.get("thumb")
                )

            if download_url:
                # Caption extraction differs for share.file vs photo/video:
                #   - share.file: `title` is the filename, `description` is the caption.
                #   - photo/video/voice: either field carries user-typed caption.
                original_name: Optional[str] = None
                if isinstance(content_data, dict):
                    if msg_type_zalo == "share.file":
                        caption = content_data.get("description") or ""
                        original_name = (
                            params_dict.get("fileName")
                            or content_data.get("title")
                            or None
                        )
                    else:
                        caption = (
                            content_data.get("description")
                            or content_data.get("title")
                            or ""
                        )
                    caption = caption.strip() if isinstance(caption, str) else ""
                    if caption:
                        content = caption

                message_type = "image" if msg_type_zalo == "chat.photo" else "file"
                folder_path = get_folder_structure("Zalo", conv_id)

                # Determine extension: fileExt (share.file) > URL suffix > msgType default
                ext = params_dict.get("fileExt") if params_dict else None
                if not ext:
                    url_path = urlparse(download_url).path
                    if "." in url_path.rsplit("/", 1)[-1]:
                        ext = url_path.rsplit(".", 1)[-1].lower()
                if not ext:
                    ext = {
                        "chat.photo": "jpg",
                        "chat.video": "mp4",
                        "chat.voice": "m4a",
                    }.get(msg_type_zalo, "bin")

                filename = build_media_filename(message_type, original_name, ext)
                local_path = os.path.join("/tmp/downloads", folder_path, filename)

                if download_file_generic(download_url, local_path):
                    s3_key = f"{folder_path}/{filename}"
                    s3_url = upload_to_s3(local_path, s3_key)
                    if s3_url:
                        media_url = s3_url

        msg_data = {
            "platform_name": "Zalo",
            "message_type": message_type,
            "media_url": media_url,
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
        media_url: Optional[str] = None

        # Baileys service decrypts E2E media and exposes plaintext via data.media.url.
        # We just fetch it over plain HTTP, same as Zalo/Telegram.
        media_info = data_field.get("media")
        media_info = media_info if isinstance(media_info, dict) else {}
        download_url = media_info.get("url")

        if download_url:
            _mime_ext_map = {
                "application/pdf": "pdf",
                "application/zip": "zip",
                "image/jpeg": "jpg",
                "image/png": "png",
                "image/webp": "webp",
                "image/gif": "gif",
                "video/mp4": "mp4",
                "video/3gpp": "3gp",
                "audio/ogg": "ogg",
                "audio/mpeg": "mp3",
                "audio/mp4": "m4a",
                "audio/aac": "aac",
            }

            # Extension: original filename > mimetype map > fallback
            ext = None
            fname = media_info.get("filename") or ""
            if "." in fname:
                ext = fname.rsplit(".", 1)[-1].lower()
            if not ext:
                ext = _mime_ext_map.get(
                    media_info.get("mimetype"),
                    {
                        "image": "jpg",
                        "video": "mp4",
                        "audio": "ogg",
                        "sticker": "webp",
                    }.get(media_info.get("type"), "bin"),
                )

            m_kind = (media_info.get("type") or "").lower()
            m_mime = (media_info.get("mimetype") or "").lower()
            if m_kind in ("image", "sticker") or m_mime.startswith("image/"):
                message_type = "image"
            else:
                message_type = "file"
            folder_path = get_folder_structure("Whatsapp", conv_id)
            filename = build_media_filename(
                message_type, media_info.get("filename"), ext
            )
            local_path = os.path.join("/tmp/downloads", folder_path, filename)

            if download_file_generic(download_url, local_path):
                s3_key = f"{folder_path}/{filename}"
                s3_url = upload_to_s3(local_path, s3_key)
                if s3_url:
                    media_url = s3_url
            else:
                logger.warning(
                    f"Failed to download WhatsApp media for message {message_id} from {download_url}"
                )

        msg_data = {
            "platform_name": "Whatsapp",
            "message_type": message_type,
            "media_url": media_url,
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
        media_url: Optional[str] = None
        file_id = None
        ext = "bin"
        media_kind: str = ""  # "image" or "file"
        original_name: Optional[str] = None

        if "photo" in message and message["photo"]:
            # Get largest photo
            file_id = message["photo"][-1]["file_id"]
            ext = "jpg"
            media_kind = "image"
        elif "document" in message:
            doc = message["document"]
            file_id = doc["file_id"]
            original_name = doc.get("file_name")
            ext = (
                original_name.split(".")[-1] if original_name and "." in original_name else "doc"
            )
            doc_mime = (doc.get("mime_type") or "").lower()
            media_kind = "image" if doc_mime.startswith("image/") else "file"
        elif "video" in message:
            file_id = message["video"]["file_id"]
            ext = "mp4"
            media_kind = "file"
            original_name = message["video"].get("file_name")
        elif "voice" in message:
            file_id = message["voice"]["file_id"]
            ext = "ogg"
            media_kind = "file"

        if file_id and token:
            message_type = media_kind or "file"
            folder_path = get_folder_structure("Telegram", str(chat.get("id")))
            filename = build_media_filename(message_type, original_name, ext)
            local_path = os.path.join("/tmp/downloads", folder_path, filename)

            if download_telegram_file(file_id, token, local_path):
                s3_key = f"{folder_path}/{filename}"
                s3_url = upload_to_s3(local_path, s3_key)
                if s3_url:
                    media_url = s3_url

        msg_data = {
            "platform_name": "Telegram",
            "message_type": message_type,
            "media_url": media_url,
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
