"""
Celery tasks for message processing and agent communication.
"""

import logging
from typing import Any, Callable, Optional, Dict, List, Protocol

import json
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
    """Get conversation info from Redis cache or API (TTL: 300s)."""
    cache_key = f"conv_info:{conversation_id}"
    cached = redis_client.get(cache_key)
    if cached:
        try:
            return json.loads(cached)
        except json.JSONDecodeError:
            pass

    info = get_conversation_info(conversation_id)
    if info:
        redis_client.setex(cache_key, 300, json.dumps(info))
    return info

def _get_cached_conversation_members(conversation_id: str) -> Optional[List[Dict[str, Any]]]:
    """Get conversation members from Redis cache or API (TTL: 300s)."""
    cache_key = f"conv_members:{conversation_id}"
    cached = redis_client.get(cache_key)
    if cached:
        try:
            return json.loads(cached)
        except json.JSONDecodeError:
            pass

    members_data = get_conversation_members(conversation_id)
    if members_data is not None:
        redis_client.setex(cache_key, 300, json.dumps(members_data))
    return members_data

def handle_send_message(
    data: Dict[str, Any], callback: Optional[Callable[[str, Dict[str, Any], Any], None]] = None
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

    # DEBOUNCE CHECK 2 (QUESTION LEVEL):
    # Only proceed if this is still the latest question scheduled.
    latest_question_id = redis_client.get(f"latest_question_message:{conversation_id}")
    if latest_question_id and str(latest_question_id) != str(message_id):
        logger.info(
            "Newer question (%s) exists for conversation %s, skipping agent answer for old msg %s",
            latest_question_id, conversation_id, message_id
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
    redis_client.setex(f"bot_processing:{conversation_id}", 60, "1")

    agent_response = call_agent_webhook(agent_payload)

    # Release processing lock
    redis_client.delete(f"bot_processing:{conversation_id}")

    if not agent_response:
        logger.error("Agent webhook call failed")
        return

    try:
        response_data = agent_response.json()
    except ValueError:
        logger.error("Failed to parse agent response as JSON")
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
                "platform_name": platform_name,
                "token": token,
                "content": f"Có tin nhắn mới cần trợ giúp từ {title}",
            }
            send_message.apply_async(
                args=(admin_payload,), queue="celery_send_message"
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
    }
    send_message.apply_async(
        args=(customer_payload,), queue="celery_send_message"
    )


@app.task(name="tasks.new_msg", queue="celery_receive_message")
def process_message(data: Dict[str, Any]) -> None:
    """
    Process incoming message: sync to backend and check if agent assistance is needed.
    """
    logger.info("Processing incoming message for %s", data.get("platform_name"))

    # Sync message to Strapi
    sync_response = sync_message(data)
    if not sync_response:
        return

    # Extract conversation and message IDs
    try:
        noti_data = sync_response.json().get("data", [])
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
    members = _get_cached_conversation_members(conversation_id)
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

    # NEW DEBOUNCE LOGIC (1-minute window):
    redis_client.setex(f"latest_user_message:{conversation_id}", 3600, str(message_id))
    logger.info("Set latest user message for %s to %s", conversation_id, message_id)

    # Schedule the check question task to run after 1 minute
    task_check_question.apply_async(
        args=(data, conversation_id, message_id, conversation_info),
        countdown=60
    )
    logger.info(
        "Scheduled check question task for conversation %s, msg %s in 60s",
        conversation_id, message_id
    )


@app.task(name="tasks.task_check_question", queue="celery_receive_message")
def task_check_question(
    data: Dict[str, Any],
    conversation_id: str,
    message_id: str,
    conversation_info: Dict[str, Any],
) -> None:
    """Schedule agent check task if the question is valid, with debouncing."""
    # DEBOUNCE CHECK 1: Ensure this is the latest message from the 1-minute window
    latest_msg_id = redis_client.get(f"latest_user_message:{conversation_id}")
    if latest_msg_id and str(latest_msg_id) != str(message_id):
        logger.info(
            "Newer message (%s) exists for conversation %s, skipping check question task for %s",
            latest_msg_id, conversation_id, message_id
        )
        return

    # Fetch history up to this message
    history = get_message_history(str(conversation_id), str(message_id))
    if not history:
        logger.warning("No message history found for %s during check_question", conversation_id)
        return

    # Extract recent user messages (e.g. from the last minute or last 5 unhandled messages)
    # We will simply collect the content of up to 5 consecutive user messages at the end
    user_messages = []
    for msg in reversed(history):  # Read from newest to oldest
        if msg.get("sender_type") == "customer":
            user_messages.append(str(msg.get("content", "")))
        else:
            break # Stop at bot/admin message

        if len(user_messages) >= 5:
            break

    user_messages.reverse() # Back to chronological order
    combined_content = " ".join(user_messages)

    if not combined_content.strip():
        logger.warning("No valid customer content to check for %s", conversation_id)
        return

    logger.info("Checking combined question content: %s", combined_content)

    check_response = check_question(combined_content)

    if not check_response:
        return

    try:
        if check_response.json().get("output") != "true":
            logger.info("Content is not considered a question for agent. Stopping.")
            return
    except ValueError:
        logger.error("Failed to parse response from check_question")
        return

    time_to_use_agent = conversation_info.get("time_to_use_agent", 0)

    # SET QUESTION DEBOUNCE KEY: We track the latest question that was scheduled
    redis_client.setex(f"latest_question_message:{conversation_id}", 3600, str(message_id))
    logger.info("Set latest question message for %s to %s", conversation_id, message_id)

    agent_check_data = {
        "conversation": conversation_id,
        "message_id": message_id,
        "time_to_use_agent": time_to_use_agent,
        "content": combined_content,  # Pass the combined content
        "type": conversation_info.get("type"),
        "platform_conv_id": data.get("platform_conv_id"),
        "group_id": data.get("platform_conv_id"),
        "user_id": data.get("platform_user_id"),
        "platform_name": data.get("platform_name"),
        "bot_message": conversation_info.get("bot_message", ""),
        "token": data.get("token"),
        "title": conversation_info.get("title"),
        "bot_sent_to": conversation_info.get("bot_sent_to"),
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
def send_message(data: Dict[str, Any]) -> None:
    """
    Send message and update Strapi with the result.
    """

    def on_success_callback(
        platform: str, message_data: Dict[str, Any], send_result: Any
    ) -> None:
        """Callback executed after successful message send."""
        update_payload = update_message_platform(platform, message_data, send_result)

        if not message_data.get("message_id"):
            return

        # Update message status in Strapi
        response = update_message(update_payload)
        if not response:
            logger.error("Failed to update message %s", message_data.get("message_id"))
            return

    handle_send_message(data, callback=on_success_callback)
