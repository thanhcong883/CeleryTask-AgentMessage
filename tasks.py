"""
Celery tasks for message processing and agent communication.
"""

import hashlib
import logging
import json
from typing import Any, Callable, Optional, Dict, List, Protocol
import os
from celery import Celery
from database import redis_client

from provider import PROVIDERS
import config
from update_message import update_message_platform
from api_client import (
    get_conversation_info,
    get_conversation_members,
    get_message_history,
    sync_message,
    update_message,
    save_bot_message,
    call_agent_webhook,
    check_question,
    find_user_role,
    build_history_chat,
)


class Provider(Protocol):
    def send(self, data: Dict[str, Any]) -> Any: ...


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize Celery app
app = Celery("my_app", broker=config.REDIS_URL)


def _mask_sensitive_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Helper to mask tokens in logs."""
    if not isinstance(data, dict):
        return data
    safe_data = data.copy()
    if "token" in safe_data:
        safe_data["token"] = "***"
    return safe_data


def _get_cached_conversation_info(conversation_id: str) -> Optional[Dict[str, Any]]:
    cache_key = f"conv_info:{conversation_id}"
    cached_data = redis_client.get(cache_key)
    if cached_data:
        try:
            logger.info("Cache hit for conversation info %s", conversation_id)
            return json.loads(str(cached_data))
        except json.JSONDecodeError:
            logger.error("JSON decode error for conversation info %s", conversation_id)
            pass

    logger.info(
        "Cache miss for conversation info %s. Fetching from API.", conversation_id
    )
    info = get_conversation_info(conversation_id)
    if info:
        redis_client.setex(cache_key, 300, json.dumps(info))
        logger.info(
            "Successfully fetched and cached conversation info %s", conversation_id
        )
    return info


def _get_cached_conversation_members(
    conversation_id: str,
) -> Optional[List[Dict[str, Any]]]:
    cache_key = f"conv_members:{conversation_id}"
    cached_data = redis_client.get(cache_key)
    if cached_data:
        try:
            logger.info("Cache hit for conversation members %s", conversation_id)
            return json.loads(str(cached_data))
        except json.JSONDecodeError:
            logger.error(
                "JSON decode error for conversation members %s", conversation_id
            )
            pass

    logger.info(
        "Cache miss for conversation members %s. Fetching from API.", conversation_id
    )
    members = get_conversation_members(conversation_id)
    if members:
        redis_client.setex(cache_key, 300, json.dumps(members))
        logger.info(
            "Successfully fetched and cached conversation members %s", conversation_id
        )
    return members


def handle_send_message(
    data: Dict[str, Any],
    callback: Optional[Callable[[str, Dict[str, Any], Any], None]] = None,
) -> Any:
    """
    Logic to send message to platform and call success callback.
    """
    platform = data.get("platform_name")
    if platform not in PROVIDERS:
        logger.error("Platform %s not supported for sending", platform)
        return None

    try:
        # data may contains token, use it if available
        # if not, provider should handle it (e.g. from config)
        result = PROVIDERS[platform].send(data)

        if callback:
            callback(platform, data, result)

        return result
    except Exception as e:
        logger.error("Failed to send message to %s: %s", platform, e)
        return None


@app.task(name="tasks.check_agent_answer", queue="celery_receive_message")
def check_agent_answer(data: Dict[str, Any]) -> None:
    """
    Celery task to check if an agent should answer a question.
    """
    conversation_id = data.get("conversation")
    message_id = data.get("message_id")

    # DEBOUNCE CHECK (Level 2):
    # Only proceed if this is still the latest valid question from the user.
    latest_question_id = redis_client.get(f"latest_question_message:{conversation_id}")
    if latest_question_id and str(latest_question_id) != str(message_id):
        logger.info(
            "Newer question (%s) exists for conversation %s, skipping agent check for %s",
            latest_question_id,
            conversation_id,
            message_id,
        )
        return

    # If the bot is currently processing an answer for another message, we can choose to skip or wait.
    if redis_client.get(f"bot_processing:{conversation_id}"):
        logger.info(
            "Bot is currently processing another answer for %s. Skipping this check.",
            conversation_id,
        )
        return

    # Fetch message history
    history = get_message_history(str(conversation_id), str(message_id))
    if history is None:
        logger.warning("No message history found for %s", conversation_id)
        return

    # Call agent to check if it can answer
    agent_payload = {
        "question": data.get("content"),
        "history_chat": build_history_chat(history),
    }

    # Set processing lock
    logger.info("Acquiring bot_processing lock for conversation %s", conversation_id)
    redis_client.setex(f"bot_processing:{conversation_id}", 60, "1")

    logger.info(
        "Calling LLM_AGENT_API for conversation %s with msg %s",
        conversation_id,
        message_id,
    )
    agent_response = call_agent_webhook(agent_payload)

    # Release processing lock
    logger.info("Releasing bot_processing lock for conversation %s", conversation_id)
    redis_client.delete(f"bot_processing:{conversation_id}")

    if not agent_response:
        logger.error(
            "Agent webhook call failed entirely for conversation %s", conversation_id
        )
        return

    try:
        response_data = agent_response.json()
        logger.info(
            "LLM_AGENT_API responded successfully for %s: %s",
            conversation_id,
            response_data,
        )
    except ValueError:
        logger.error(
            "Failed to parse agent response as JSON for conversation %s",
            conversation_id,
        )
        return

    # If agent cannot answer, notify admins
    if response_data.get("output") == "false":
        logger.info("Agent could not answer, notifying human agents")
        _notify_admins_and_customer(data)


def _notify_admins_and_customer(data: Dict[str, Any]) -> None:
    """Send notifications to admins and customer when agent cannot answer."""
    platform_name = data.get("platform_name")
    title = data.get("title", "")
    token = data.get("token")

    media_hint = {
        "image": " (có kèm ảnh)",
        "file": " (có kèm file)",
    }.get(data.get("message_type"), "")

    # Notify each admin conversation
    bot_sent_to = data.get("bot_sent_to", [])
    if bot_sent_to:
        for conversation_id in bot_sent_to:
            conv_info = _get_cached_conversation_info(conversation_id)
            if not conv_info:
                logger.warning(
                    "Could not retrieve info for admin conversation %s", conversation_id
                )
                continue

            admin_payload = {
                "type": conv_info.get("type"),
                "group_id": conv_info.get("platform_conv_id"),
                "user_id": conv_info.get("platform_conv_id"),
                "platform_conv_id": conv_info.get("platform_conv_id"),
                "platform_name": "Telegram",
                "token": os.environ.get("TELEGRAM_TOKEN_SUPPORT"),
                "content": (
                    f"Có tin nhắn mới cần trợ giúp từ nền tảng {platform_name}, "
                    f"nhóm {title}{media_hint}"
                ),
            }
            logger.info("Admin payload: %s", admin_payload)
            send_message.apply_async(
                args=(admin_payload, "bot"), queue="celery_send_message"
            )

    # Notify customer
    customer_payload = {
        "type": data.get("type"),
        "group_id": data.get("group_id"),
        "content": data.get("bot_message"),
        "platform_name": platform_name,
        "platform_conv_id": data.get("platform_conv_id"),
        "token": token,
        "user_id": data.get("user_id"),
        "bot_id": data.get("bot_id"),
    }
    logger.info("Customer payload: %s", customer_payload)
    send_message.apply_async(
        args=(customer_payload, "bot"), queue="celery_send_message"
    )


@app.task(name="tasks.new_msg", queue="celery_receive_message")
def process_message(data: Dict[str, Any]) -> None:
    """
    Process incoming message: sync to backend and check if agent assistance is needed.
    """
    logger.info("Processing incoming message for %s", data.get("platform_name"))

    # Handling cases for self-sent messages (Bot, Admin UI or Admin Zalo App)
    if data.get("isSelf"):
        msg_id = data.get("platform_msg_id")
        content = data.get("content", "")
        platform_conv_id = data.get("platform_conv_id")
        content_hash = hashlib.md5((content or "").encode()).hexdigest()

        # Check 1: msgId mark (set in on_success_callback)
        # Check 2: Content Hash mark (set in provider.py before sending)
        if (msg_id and redis_client.get(f"handled_msg:{msg_id}")) or redis_client.get(
            f"bot_sent:{platform_conv_id}:{content_hash}"
        ):
            logger.info(
                "Bot/Admin system echo detected (by msgId or content-hash). Skipping."
            )
            return

        # Case 3: Admin used Zalo App directly -> Sync to Strapi then stop
        logger.info("Admin manual message detected. Syncing and stopping.")
        sync_message(data)
        return

    # Case 4: Customer message -> Sync and proceed to Agent logic
    logger.info(
        "Syncing customer message to Strapi for msg_id: %s", data.get("platform_msg_id")
    )
    sync_response = sync_message(data)
    if not sync_response:
        return

    # Extract conversation and message IDs
    try:
        noti_data = sync_response.json().get("data", [])
        logger.info("Sync response: %s", noti_data)
        if not noti_data:
            logger.error("Empty response from sync message API")
            return

        first_item = noti_data[0].get("data", {})
        conversation_id = first_item.get("conversationId")
        message_id = first_item.get("messageId")

        if not conversation_id or not message_id:
            logger.error("Missing conversationId or messageId in sync response")
            return
    except (ValueError, IndexError, KeyError) as e:
        logger.error("Failed to parse sync response: %s", e)
        return

    # Get conversation info
    conversation_info = _get_cached_conversation_info(conversation_id)
    if not conversation_info:
        logger.warning("Could not retrieve conversation info for %s", conversation_id)
        return

    use_agent = conversation_info.get("use_agent")
    group_admin = conversation_info.get("group_admin")

    # Only process if agent is enabled and not an admin group
    if not (use_agent is True and group_admin is False):
        return

    # Check user role - skip if admin
    members = get_conversation_members(conversation_id)
    if not members:
        return

    platform_user_id = data.get("platform_user_id")
    if not platform_user_id:
        return

    user_role = find_user_role(members, str(platform_user_id))
    if user_role == "admin":
        # Admin responded: Lock bot for 30 minutes
        redis_client.setex(f"admin_active:{conversation_id}", 1800, "1")
        logger.info(
            "Admin active in conversation %s, bot paused for 30 mins.", conversation_id
        )
        return

    # Check if admin is currently active
    if redis_client.get(f"admin_active:{conversation_id}"):
        logger.info(
            "Skipping agent check for %s because an admin is active.", conversation_id
        )
        return

    # NEW DEBOUNCE LOGIC:
    # 1. Capture the FIRST message ID of this 1-minute window to fetch history properly
    first_msg_key = f"first_user_message:{conversation_id}"
    if not redis_client.get(first_msg_key):
        redis_client.setex(first_msg_key, 3600, str(message_id))
        logger.info(
            "Set FIRST user message for window %s to %s", conversation_id, message_id
        )
    else:
        logger.info(
            "FIRST user message for window %s already exists (is %s), continuing debounce...",
            conversation_id,
            redis_client.get(first_msg_key),
        )

    # 2. Update the LATEST message ID to handle debounce override
    redis_client.setex(f"latest_user_message:{conversation_id}", 3600, str(message_id))
    logger.info(
        "Set latest user message for %s to %s. Scheduling task_check_question.",
        conversation_id,
        message_id,
    )

    # Schedule task_check_question after 60 seconds (1 minute window)
    task_check_question.apply_async(
        args=(data, str(conversation_id), str(message_id), conversation_info),
        countdown=60,
    )


@app.task(name="tasks.task_check_question", queue="celery_receive_message")
def task_check_question(
    data: Dict[str, Any],
    conversation_id: str,
    message_id: str,
    conversation_info: Dict[str, Any],
) -> None:
    """Task to evaluate concatenated recent messages after a 1-minute debounce window."""

    # 1. Check debounce
    latest_msg_id = redis_client.get(f"latest_user_message:{conversation_id}")
    if latest_msg_id and str(latest_msg_id) != str(message_id):
        logger.info(
            "Newer message (%s) arrived for conversation %s, skipping check for %s",
            latest_msg_id,
            conversation_id,
            message_id,
        )
        return

    # 2. Get history using the FIRST message ID of the window
    first_msg_key = f"first_user_message:{conversation_id}"
    first_msg_id_bytes = redis_client.get(first_msg_key)
    first_msg_id = str(first_msg_id_bytes) if first_msg_id_bytes else str(message_id)

    # Delete the key so the next batch can start fresh
    redis_client.delete(first_msg_key)

    history = get_message_history(str(conversation_id), str(first_msg_id))
    if not history:
        logger.warning(
            "No message history found for %s starting at %s",
            conversation_id,
            first_msg_id,
        )
        return

    logger.info(
        "Fetched %d messages from history for conversation %s starting at %s",
        len(history),
        conversation_id,
        first_msg_id,
    )

    # 3. Gom tin nhắn (Concatenate messages)
    customer_messages = []

    # Depending on the API, if passing 1676 returns [1676, 1677, 1678], it's from oldest to newest.
    # If it returns [1678, 1677, 1676], it's newest to oldest.
    # Usually we want chronological order for the AI: "Help \n Giúp tôi với \n Hihi"

    # Let's ensure we process them correctly. If the API returns them chronologically (oldest first):
    for msg in history:
        if msg.get("sender_type") != "customer":
            # If an admin or bot replied in the middle, we stop collecting.
            break

        content_msg = msg.get("content")
        if content_msg:
            customer_messages.append(str(content_msg))

        if len(customer_messages) >= 5:
            break

    if not customer_messages:
        logger.info("No customer messages found to check for %s", conversation_id)
        return

    # If the history was newest-to-oldest, we'd reverse it. But given the previous log,
    # if passing 1676 returns 1677, 1678, it's chronological (oldest to newest).
    # So we don't need to reverse.
    concatenated_content = "\n".join(customer_messages)

    logger.info(
        "Checking question for conversation %s: %s",
        conversation_id,
        concatenated_content,
    )

    # 4. Check if question
    check_response = check_question(concatenated_content)

    if not check_response:
        logger.error("check_question API returned no response for %s", conversation_id)
        return

    try:
        is_question = check_response.json().get("output")
        logger.info("AI check_question result for %s: %s", conversation_id, is_question)
        if is_question != "true":
            logger.info(
                "Message evaluated as NOT a question. Aborting agent check for %s",
                conversation_id,
            )
            return
    except ValueError:
        logger.error("Failed to parse response from check_question")
        return

    # 5. Question detected: Update latest_question_message and schedule agent check
    redis_client.setex(
        f"latest_question_message:{conversation_id}", 3600, str(message_id)
    )
    logger.info(
        "Valid question detected for %s. Set latest_question_message to %s",
        conversation_id,
        message_id,
    )

    time_to_use_agent = conversation_info.get("time_to_use_agent", 0)

    bot_id = (
        (conversation_info.get("account") or {}).get("account_id")
        or data.get("bot_id")
        or data.get("account_id")
    )

    if not bot_id:
        logger.warning(
            "bot_id is missing for conversation %s. This may cause sending errors for Zalo/WhatsApp.",
            conversation_id,
        )

    agent_check_data = {
        "conversation": conversation_id,
        "message_id": message_id,
        "time_to_use_agent": time_to_use_agent,
        "content": concatenated_content,  # passing the concatenated content
        "type": conversation_info.get("type"),
        "platform_conv_id": data.get("platform_conv_id"),
        "group_id": data.get("platform_conv_id"),
        "user_id": data.get("platform_user_id"),
        "platform_name": data.get("platform_name"),
        "bot_message": conversation_info.get("bot_message", ""),
        "token": data.get("token"),
        "title": conversation_info.get("title"),
        "bot_sent_to": conversation_info.get("bot_sent_to"),
        "bot_id": bot_id,
        "media_url": data.get("media_url"),
        "message_type": data.get("message_type", "text"),
    }

    check_agent_answer.apply_async(
        args=(agent_check_data,), countdown=int(time_to_use_agent)
    )
    logger.info(
        "Scheduled agent check for conversation %s, msg %s in %ds",
        conversation_id,
        message_id,
        int(time_to_use_agent),
    )


@app.task(name="tasks.send_message", queue="celery_send_message")
def send_message(data: Dict[str, Any], sender_type: str = "admin") -> None:
    """
    Send message and update Strapi with the result.
    """

    def on_success_callback(
        platform: str, message_data: Dict[str, Any], send_result: Any
    ) -> None:
        """Callback executed after successful message send."""
        logger.info(
            "on_success_callback: platform=%s, send_result=%s", platform, send_result
        )
        update_payload = update_message_platform(platform, message_data, send_result)
        logger.info(
            "on_success_callback: update_payload=%s", update_payload
        )

        # Mark this platform_msg_id as already handled by our system to avoid echo sync
        platform_msg_id = update_payload.get("platform_msg_id")
        if platform_msg_id:
            redis_client.setex(f"handled_msg:{platform_msg_id}", 3600, "1")

        if sender_type == "bot":
            save_bot_message(message_data)
        logger.info("Save bot message success: %s", message_data)
        # Update message status in Strapi
        if not message_data.get("message_id"):
            logger.warning(
                "on_success_callback: No message_id in data, skipping update"
            )
            return
        response = update_message(update_payload)
        logger.info("Update message response: %s", response)
        if not response:
            logger.error("Failed to update message %s", message_data.get("message_id"))
            return

    handle_send_message(data, callback=on_success_callback)
