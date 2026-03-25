"""
Celery tasks for message processing and agent communication.
"""

import logging
from typing import Any, Callable, Optional, Dict, List, Protocol

from celery import Celery
import redis

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

# Initialize Redis Client for debouncing and state management
redis_client = redis.from_url(config.REDIS_URL)


def _mask_sensitive_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Helper to mask tokens in logs."""
    if not isinstance(data, dict):
        return data
    safe_data = data.copy()
    if "token" in safe_data:
        safe_data["token"] = "***"
    return safe_data


# =============================================================================
# Message Handlers
# =============================================================================


def handle_send_message(
    data: Dict[str, Any],
    callback: Optional[Callable[[str, Dict[str, Any], Any], None]] = None,
) -> None:
    """
    Send message through the appropriate platform provider.

    Args:
        data: Message data containing platform_id and message content
        callback: Optional callback function to execute on success
    """
    platform: Optional[str] = data.get("platform_name")
    if not platform:
        logger.error("Platform name missing in message data")
        return

    provider: Optional[Provider] = PROVIDERS.get(platform.title())
    if not provider:
        logger.error("Platform '%s' not supported", platform)
        return

    try:
        logger.info("Sending message via %s: %s", platform, _mask_sensitive_data(data))
        result = provider.send(data)
        if callback:
            callback(platform, data, result)
        logger.info("Message sent successfully via %s", platform)
    except Exception as e:
        logger.error("Failed to send message via %s: %s", platform, e, exc_info=True)


# =============================================================================
# Celery Tasks
# =============================================================================


@app.task(name="task.agent_message", queue="celery_agent_message")
def check_agent_answer(data: Dict[str, Any]) -> None:
    """
    Check if agent can answer the question and notify admins if needed.

    Args:
        data: Contains conversation, message_id, content, and notification settings
    """
    conversation_id = data.get("conversation")
    message_id = data.get("message_id")
    content = data.get("content")

    if not conversation_id or not message_id or not content:
        logger.error("Required fields missing in agent message data")
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

    agent_response = call_agent_webhook(agent_payload)
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
            conv_info = get_conversation_info(conversation_id)
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
                args=(admin_payload, admin_payload), queue="celery_send_message"
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
        args=(customer_payload, customer_payload), queue="celery_send_message"
    )


@app.task(name="tasks.new_msg", queue="celery_receive_message")
def process_message(data: Dict[str, Any]) -> None:
    """
    Process incoming message: sync to backend and check if agent assistance is needed.

    Args:
        data: Incoming message data from platform
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
    conversation_info = get_conversation_info(conversation_id)
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

    # Check if admin is currently active or bot is already processing a question
    if redis_client.get(f"admin_active:{conversation_id}"):
        logger.info(
            "Skipping agent check for %s because an admin is active.", conversation_id
        )
        return

    if redis_client.get(f"bot_processing:{conversation_id}"):
        logger.info(
            "Skipping agent check for %s because bot is already processing a recent question.",
            conversation_id,
        )
        return

    # Check if the question needs agent processing
    _schedule_agent_check(data, conversation_id, message_id, conversation_info)


def _schedule_agent_check(
    data: Dict[str, Any],
    conversation_id: str,
    message_id: str,
    conversation_info: Dict[str, Any],
) -> None:
    """Schedule agent check task if the question is valid."""
    content = data.get("content")
    if not content:
        return

    check_response = check_question(str(content))

    if not check_response:
        return

    try:
        if check_response.json().get("output") != "true":
            return
    except ValueError:
        logger.error("Failed to parse response from check_question")
        return

    time_to_use_agent = conversation_info.get("time_to_use_agent", 0)

    # Question is valid: Lock bot from answering subsequent questions for time_to_use_agent + buffer
    # The buffer ensures that the bot has time to finish answering the first question
    lock_time = int(time_to_use_agent) + 60
    redis_client.setex(f"bot_processing:{conversation_id}", lock_time, "1")
    logger.info(
        "Bot processing locked for conversation %s for %d seconds.",
        conversation_id,
        lock_time,
    )

    agent_check_data = {
        "conversation": conversation_id,
        "message_id": message_id,
        "time_to_use_agent": time_to_use_agent,
        "content": data.get("content"),
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
        "Scheduled agent check for conversation %s in %ds",
        conversation_id,
        int(time_to_use_agent),
    )


@app.task(name="tasks.send_message", queue="celery_send_message")
def send_message(
    data: Dict[str, Any], data_send: Optional[Dict[str, Any]] = None
) -> None:
    """
    Send message and update Strapi with the result.

    Args:
        data: Message data to send
        data_send: Optional data for bot-sent message logging
    """

    def on_success_callback(
        platform: str, message_data: Dict[str, Any], send_result: Any
    ) -> None:
        """Callback executed after successful message send."""
        update_payload = update_message_platform(platform, message_data, send_result)

        # Update message status in Strapi
        response = update_message(update_payload)
        if not response:
            logger.error("Failed to update message %s", message_data.get("message_id"))
            return

        # Save bot-sent message if applicable
        if data_send:
            _save_bot_sent_message(update_payload, data_send)

    handle_send_message(data, callback=on_success_callback)


def _save_bot_sent_message(
    update_payload: Dict[str, Any], data_send: Dict[str, Any]
) -> None:
    """Save bot-sent message to Strapi."""
    bot_message_data = {
        "sender_type": "bot",
        "sender_id": "",
        "platform_msg_id": update_payload.get("platform_msg_id"),
        "content": data_send.get("content"),
        "datetime": update_payload.get("datetime"),
        "platform_conv_id": data_send.get("platform_conv_id"),
        "message_status": "sent",
    }

    response = save_bot_message(bot_message_data)
    if response:
        logger.info(
            "Bot message saved for conversation %s", data_send.get("platform_conv_id")
        )
