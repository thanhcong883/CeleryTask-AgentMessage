"""
API client utilities for making HTTP requests to backend services.
"""

import logging
from typing import Optional, Dict, Any, List

import requests
from requests.exceptions import RequestException

import config

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def _mask_sensitive_data(data: Any) -> Any:
    """Mask sensitive data in dict for logging."""
    if not isinstance(data, dict):
        return data
    safe_data = data.copy()
    if "token" in safe_data:
        safe_data["token"] = "***"
    return safe_data


# Constants
DEFAULT_TIMEOUT = 10
JSON_HEADERS = {"Content-Type": "application/json"}


# =============================================================================
# Base HTTP Methods
# =============================================================================


def api_get(
    url: str, headers: Optional[Dict[str, Any]] = None, timeout: int = DEFAULT_TIMEOUT
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
        logger.info("API Request (GET): %s", url)
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        logger.info("API Response (GET): %s - Status: %s", url, response.status_code)
        return response
    except RequestException as e:
        logger.error("GET request failed for %s: %s", url, e)
        return None


def api_post(
    url: str,
    json_data: Dict[str, Any],
    headers: Optional[Dict[str, Any]] = None,
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
        logger.info(
            "API Request (POST): %s - Data: %s", url, _mask_sensitive_data(json_data)
        )
        response = requests.post(url, json=json_data, headers=headers, timeout=timeout)
        response.raise_for_status()
        logger.info("API Response (POST): %s - Status: %s", url, response.status_code)
        return response
    except RequestException as e:
        logger.error("POST request failed for %s: %s", url, e)
        return None


def api_put(
    url: str,
    json_data: Dict[str, Any],
    headers: Optional[Dict[str, Any]] = None,
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
        logger.info(
            "API Request (PUT): %s - Data: %s", url, _mask_sensitive_data(json_data)
        )
        response = requests.put(url, json=json_data, headers=headers, timeout=timeout)
        response.raise_for_status()
        logger.info("API Response (PUT): %s - Status: %s", url, response.status_code)
        return response
    except RequestException as e:
        logger.error("PUT request failed for %s: %s", url, e)
        return None


# =============================================================================
# Strapi API Methods
# =============================================================================


def get_conversation_info(conversation_id: str) -> Optional[Dict[str, Any]]:
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
        try:
            return response.json().get("data", {})
        except ValueError:
            logger.error("Failed to parse JSON response from GET %s", url)
    return None


def get_conversation_members(conversation_id: str) -> Optional[List[Dict[str, Any]]]:
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
        try:
            return response.json().get("data", [])
        except ValueError:
            logger.error("Failed to parse JSON response from GET %s", url)
    return None


def get_message_history(
    conversation_id: str, message_id: str
) -> Optional[List[Dict[str, Any]]]:
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
        try:
            return response.json().get("data", [])
        except ValueError:
            logger.error("Failed to parse JSON response from GET %s", url)
    return None


def sync_message(data: Dict[str, Any]) -> Optional[requests.Response]:
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


def update_message(payload: Dict[str, Any]) -> Optional[requests.Response]:
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


def save_bot_message(data: Dict[str, Any]) -> Optional[requests.Response]:
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


def call_agent_webhook(payload: Dict[str, Any]) -> Optional[requests.Response]:
    """
    Call the N8N agent webhook.

    Args:
        payload: Agent payload with question and history

    Returns:
        Response object if successful, None otherwise
    """
    import os
    import json
    try:
        from openai import OpenAI
    except ImportError:
        logger.error("openai package is not installed.")
        return None

    try:
        client = OpenAI(
            base_url="https://ark.ap-southeast.bytepluses.com/api/v3",
            api_key=os.environ.get("ARK_API_KEY"),
        )
        
        question = payload.get("question", "")
        history_chat = json.dumps(payload.get("history_chat", []), ensure_ascii=False)
        
        system_prompt = f"""ROLE:
You are a strict answer-verification engine.

You are NOT allowed to infer, assume, or add information.
You must ONLY use the provided Question and Chat history.

DEFINITIONS:

A message is considered a VALID HANDLING if:
1. The role is "admin" or "bot"
AND
2. The message satisfies AT LEAST ONE of the following:

   A. DIRECT ANSWER
      - Directly resolves the question
      - Provides guidance, explanation, or solution
      - Semantically answers the user's request

   B. CLARIFYING QUESTION
      - Asks for more information in order to handle the question
      - Is logically related to the question
      - Example:
        - "Bạn gặp khó khăn gì?"
        - "Lỗi xảy ra khi nào?"
        - "Bạn có thể mô tả rõ hơn không?"

If NO such message exists in the chat history, the answer is considered NONE.


INPUT:
Question:
{question}

Chat history:

{history_chat}

INSTRUCTIONS:
- Compare the question with EACH chat message.
- If ANY valid answer is found, return true.
- If NONE are found, return false.

OUTPUT:
Return ONLY:
- true
- false

Do NOT explain.
Do NOT add text."""

        response = client.chat.completions.create(
            model="ep-20260306171113-dqqlf",
            messages=[
                {"role": "user", "content": system_prompt},
            ],
            temperature=0.0,
        )

        output_text = response.choices[0].message.content.strip().lower()
        output_val = "true" if "true" in output_text else "false"

        class _DummyResponse:
            def json(self):
                return {"output": output_val}
                
        return _DummyResponse()
    except Exception as e:
        logger.error("call_agent_webhook API call failed: %s", e)
        return None


def check_question(content: str) -> Optional[requests.Response]:
    """
    Check if a question needs agent processing.

    Args:
        content: Question content to check

    Returns:
        Response object if successful, None otherwise
    """
    import os
    try:
        from openai import OpenAI
    except ImportError:
        logger.error("openai package is not installed.")
        return None

    try:
        # Initialize the Openai client to read your API Key from the environment variable
        client = OpenAI(
            # This is the default path. You can configure it based on the service location
            base_url="https://ark.ap-southeast.bytepluses.com/api/v3",
            # Get your API Key from the environment variable
            api_key=os.environ.get("ARK_API_KEY"),
        )

        system_prompt = """You are a strict binary classifier.

Task:

Determine whether the following message is a QUESTION.

Return true if the message:

- Directly asks a question OR
- Reports a problem, error, or unusual situation OR
- Expresses uncertainty or doubt that has a legitimate reason to expect confirmation, explanation, or help
- Requests assistance or to do something

Return false if the message:

- Is just a greeting or goodbye
- Is an affirmation or acknowledgment

- Is a clear statement NOT expecting a response

- Is polite or polite conversationalism"""

        response = client.chat.completions.create(
            # Specify the Ark Inference Point ID that you created, which has been changed for you here to your Endpoint ID
            model="ep-20260306171113-dqqlf",
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"Message:\n\n{content}",
                }
            ],
            temperature=0.0,
        )

        output_text = response.choices[0].message.content.strip().lower()
        output_val = "true" if "true" in output_text else "false"

        class _DummyResponse:
            def json(self):
                return {"output": output_val}
                
        return _DummyResponse()
    except Exception as e:
        logger.error("check_question API call failed: %s", e)
        return None


# =============================================================================
# Utility Functions
# =============================================================================


def find_user_role(
    members: List[Dict[str, Any]], platform_user_id: str
) -> Optional[str]:
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


def build_history_chat(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
