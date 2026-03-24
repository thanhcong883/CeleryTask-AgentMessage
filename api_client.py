"""
API client utilities for making HTTP requests to backend services.
"""

import logging
from typing import Optional

import requests
from requests.exceptions import RequestException

import config

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def _mask_sensitive_data(data: dict) -> dict:
    """Mask sensitive data in dict for logging."""
    if not isinstance(data, dict):
        return data
    safe_data = data.copy()
    if "token" in safe_data: safe_data["token"] = "***"
    return safe_data


# Constants
DEFAULT_TIMEOUT = 10
JSON_HEADERS = {"Content-Type": "application/json"}


# =============================================================================
# Base HTTP Methods
# =============================================================================


def api_get(
    url: str, headers: Optional[dict] = None, timeout: int = DEFAULT_TIMEOUT
) -> Optional[requests.Response]:
    """
    Make a GET request with error handling.

    Args:
        url: The URL to request
        headers: Optional headers to include
        timeout: Request timeout in seconds

    Returns:
        Response object if successful, None otherwise
    """
    try:
        logger.info(f"API Request (GET): {url}")
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        logger.info(f"API Response (GET): {url} - Status: {response.status_code}")
        return response
    except RequestException as e:
        logger.error(f"GET request failed for {url}: {e}")
        return None


def api_post(
    url: str,
    json_data: dict,
    headers: Optional[dict] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Optional[requests.Response]:
    """
    Make a POST request with error handling.

    Args:
        url: The URL to request
        json_data: JSON data to send
        headers: Optional headers to include
        timeout: Request timeout in seconds

    Returns:
        Response object if successful, None otherwise
    """
    try:
        logger.info(f"API Request (POST): {url} - Data: {_mask_sensitive_data(json_data)}")
        response = requests.post(url, json=json_data, headers=headers, timeout=timeout)
        response.raise_for_status()
        logger.info(f"API Response (POST): {url} - Status: {response.status_code}")
        return response
    except RequestException as e:
        logger.error(f"POST request failed for {url}: {e}")
        return None


def api_put(
    url: str,
    json_data: dict,
    headers: Optional[dict] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Optional[requests.Response]:
    """
    Make a PUT request with error handling.

    Args:
        url: The URL to request
        json_data: JSON data to send
        headers: Optional headers to include
        timeout: Request timeout in seconds

    Returns:
        Response object if successful, None otherwise
    """
    try:
        logger.info(f"API Request (PUT): {url} - Data: {_mask_sensitive_data(json_data)}")
        response = requests.put(url, json=json_data, headers=headers, timeout=timeout)
        response.raise_for_status()
        logger.info(f"API Response (PUT): {url} - Status: {response.status_code}")
        return response
    except RequestException as e:
        logger.error(f"PUT request failed for {url}: {e}")
        return None


# =============================================================================
# Strapi API Methods
# =============================================================================


def get_conversation_info(conversation_id: str) -> Optional[dict]:
    """
    Fetch conversation information from Strapi.

    Args:
        conversation_id: The conversation ID to fetch

    Returns:
        Conversation data dict if successful, None otherwise
    """
    url = f"{config.STRAPI_GET_CONVERSATION}/{conversation_id}"
    response = api_get(url, headers=config.HEADERS_API_BACKEND)
    if response:
        return response.json().get("data", {})
    return None


def get_conversation_members(conversation_id: str) -> Optional[list]:
    """
    Fetch conversation members from Strapi.

    Args:
        conversation_id: The conversation ID to fetch members for

    Returns:
        List of members if successful, None otherwise
    """
    url = config.STRAPI_GET_CONVERSATION_MEMBER.format(conversation_id=conversation_id)
    response = api_get(url, headers=config.HEADERS_API_BACKEND)
    if response:
        return response.json().get("data", [])
    return None


def get_message_history(conversation_id: str, message_id: str) -> Optional[list]:
    """
    Fetch message history for a conversation.

    Args:
        conversation_id: The conversation ID
        message_id: The message ID

    Returns:
        List of messages if successful, None otherwise
    """
    url = config.STRAPI_GET_HISTORY_MESSAGE.format(
        conversation_id=conversation_id, message_id=message_id
    )
    response = api_get(url, headers=config.HEADERS_API_BACKEND)
    if response:
        return response.json().get("data", [])
    return None


def sync_message(data: dict) -> Optional[requests.Response]:
    """
    Sync message to Strapi.

    Args:
        data: Message data to sync

    Returns:
        Response object if successful, None otherwise
    """
    return api_post(
        config.STRAPI_SYNC_MESSAGE, json_data=data, headers=config.HEADERS_API_BACKEND
    )


def update_message(payload: dict) -> Optional[requests.Response]:
    """
    Update message in Strapi.

    Args:
        payload: Update payload

    Returns:
        Response object if successful, None otherwise
    """
    return api_put(
        config.STRAPI_UPDATE_MESSAGE,
        json_data=payload,
        headers=config.HEADERS_API_BACKEND,
    )


def save_bot_message(data: dict) -> Optional[requests.Response]:
    """
    Save bot-sent message to Strapi.

    Args:
        data: Bot message data

    Returns:
        Response object if successful, None otherwise
    """
    return api_post(
        config.STRAPI_SAVE_MESSAGE_BOT_SENT,
        json_data=data,
        headers=config.HEADERS_API_BACKEND,
    )


# =============================================================================
# External API Methods
# =============================================================================


def call_agent_webhook(payload: dict) -> Optional[requests.Response]:
    """
    Call the N8N agent webhook.

    Args:
        payload: Agent payload with question and history

    Returns:
        Response object if successful, None otherwise
    """
    return api_post(config.N8N_AGENT_WEBHOOK, json_data=payload, headers=JSON_HEADERS)


def check_question(content: str) -> Optional[requests.Response]:
    """
    Check if a question needs agent processing.

    Args:
        content: Question content to check

    Returns:
        Response object if successful, None otherwise
    """
    return api_post(
        config.CHECK_QUESTION_API, json_data={"content": content}, headers=JSON_HEADERS
    )


# =============================================================================
# Utility Functions
# =============================================================================


def find_user_role(members: list, platform_user_id: str) -> Optional[str]:
    """
    Find user role from member list.

    Args:
        members: List of conversation members
        platform_user_id: The platform user ID to find

    Returns:
        User role if found, None otherwise
    """
    return next(
        (
            m.get("role_app")
            for m in members
            if m.get("customer", {}).get("platform_user_id") == platform_user_id
        ),
        None,
    )


def build_history_chat(history: list) -> list:
    """
    Build history chat format for agent payload.

    Args:
        history: List of message history

    Returns:
        Formatted history list
    """
    return [
        {
            "role": msg.get("sender_type"),
            "content": msg.get("content"),
            "datetime": msg.get("datetime"),
        }
        for msg in history
    ]
