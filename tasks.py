"""
Celery tasks for message processing and agent communication.
"""

import logging
from typing import Any, Callable, Optional, Protocol

from celery import Celery

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
    def send(self, data: dict) -> Any: ...


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize Celery app
app = Celery("my_app", broker=config.REDIS_URL)


# =============================================================================
# Message Handlers
# =============================================================================


def handle_send_message(
    data: dict, callback: Optional[Callable[[str, dict, Any], None]] = None
) -> None:
    """
    Send message through the appropriate platform provider.

    Args:
        data: Message data containing platform_id and message content
        callback: Optional callback function to execute on success
    """
    platform = data.get("platform_id")
    if not platform:
        logger.error("Platform ID missing in message data")
        return

    provider: Provider = PROVIDERS.get(platform)  # type: ignore
    if not provider:
        logger.error(f"Platform '{platform}' not supported")
        return

    try:
        result = provider.send(data)
        if callback:
            callback(platform, data, result)
        logger.info(f"Message sent successfully via {platform}")
    except Exception as e:
        logger.error(f"Failed to send message via {platform}: {e}")


# =============================================================================
# Celery Tasks
# =============================================================================


@app.task(name="task.agent_message", queue="celery_agent_message")
def check_agent_answer(data: dict) -> None:
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
        return

    # Call agent to check if it can answer
    agent_payload = {
        "question": data.get("content"),
        "history_chat": build_history_chat(history),
    }

    agent_response = call_agent_webhook(agent_payload)
    if not agent_response:
        return

    # If agent cannot answer, notify admins
    if agent_response.json().get("output") == "false":
        _notify_admins_and_customer(data)


def _notify_admins_and_customer(data: dict) -> None:
    """Send notifications to admins and customer when agent cannot answer."""
    platform_id = data.get("platform_id")
    title = data.get("title", "")

    # Notify each admin conversation
    bot_sent_to = data.get("bot_sent_to", [])
    if bot_sent_to:
        for conversation_id in bot_sent_to:
            conv_info = get_conversation_info(conversation_id)
            if not conv_info:
                continue

            admin_payload = {
                "type": conv_info.get("type"),
                "group_id": conv_info.get("platform_conv_id"),
                "user_id": conv_info.get("platform_conv_id"),
                "platform_conv_id": conv_info.get("platform_conv_id"),
                "platform_id": platform_id,
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
        "platform_id": platform_id,
        "platform_conv_id": data.get("platform_conv_id"),
        "user_id": data.get("user_id"),
    }
    send_message.apply_async(
        args=(customer_payload, customer_payload), queue="celery_send_message"
    )


@app.task(name="tasks.new_msg", queue="celery_receive_message")
def process_message(data: dict) -> None:
    """
    Process incoming message: sync to backend and check if agent assistance is needed.

    Args:
        data: Incoming message data from platform
    """
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
    except (ValueError, IndexError, KeyError) as e:
        logger.error(f"Failed to parse sync response: {e}")
        return

    if not conversation_id or not message_id:
        logger.error(f"Missing conversation_id ({conversation_id}) or message_id ({message_id}) in sync response")
        return

    # Get conversation info
    conversation_info = get_conversation_info(conversation_id)
    if not conversation_info:
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
        return

    # Check if the question needs agent processing
    _schedule_agent_check(data, conversation_id, message_id, conversation_info)


def _schedule_agent_check(
    data: dict, conversation_id: str, message_id: str, conversation_info: dict
) -> None:
    """Schedule agent check task if the question is valid."""
    content = data.get("content")
    if not content:
        return

    check_response = check_question(str(content))

    if not check_response:
        return

    if check_response.json().get("output") != "true":
        return

    try:
        time_to_use_agent = int(conversation_info.get("time_to_use_agent") or 0)
    except (ValueError, TypeError):
        logger.warning(f"Invalid time_to_use_agent '{conversation_info.get('time_to_use_agent')}'. Defaulting to 0.")
        time_to_use_agent = 0

    agent_check_data = {
        "conversation": conversation_id,
        "message_id": message_id,
        "time_to_use_agent": time_to_use_agent,
        "content": data.get("content"),
        "type": conversation_info.get("type"),
        "platform_conv_id": data.get("platform_conv_id"),
        "group_id": data.get("platform_conv_id"),
        "user_id": data.get("platform_user_id"),
        "platform_id": data.get("platform_id"),
        "bot_message": conversation_info.get("bot_message", ""),
        "title": conversation_info.get("title"),
        "bot_sent_to": conversation_info.get("bot_sent_to"),
    }

    check_agent_answer.apply_async(
        args=(agent_check_data,), countdown=int(time_to_use_agent)
    )
    logger.info(
        f"Scheduled agent check for conversation {conversation_id} in {time_to_use_agent}s"
    )


@app.task(name="tasks.send_message", queue="celery_send_message")
def send_message(data: dict, data_send: Optional[dict] = None) -> None:
    """
    Send message and update Strapi with the result.

    Args:
        data: Message data to send
        data_send: Optional data for bot-sent message logging
    """

    def on_success_callback(
        platform: str, message_data: dict, send_result: Any
    ) -> None:
        """Callback executed after successful message send."""
        update_payload = update_message_platform(platform, message_data, send_result)

        # Update message status in Strapi
        response = update_message(update_payload)
        if not response:
            logger.error(f"Failed to update message {message_data.get('message_id')}")
            return

        # Save bot-sent message if applicable
        if data_send:
            _save_bot_sent_message(update_payload, data_send)

    handle_send_message(data, callback=on_success_callback)


def _save_bot_sent_message(update_payload: dict, data_send: dict) -> None:
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
            f"Bot message saved for conversation {data_send.get('platform_conv_id')}"
        )
