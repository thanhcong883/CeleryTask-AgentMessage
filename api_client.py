import os

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
    conversation_id: str, message_id: str, limit: int = 20
) -> Optional[List[Dict[str, Any]]]:
    """
    Fetch message history for a conversation.

    Args:
        conversation_id: The conversation ID
        message_id: The message ID to start from
        limit: Maximum number of messages to fetch

    Returns:
        List of messages if successful, None otherwise
    """
    url = config.STRAPI_GET_HISTORY_MESSAGE.format(
        conversation_id=conversation_id, message_id=message_id, limit=limit
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

        system_prompt = """ROLE:
You are a strict answer-verification engine.

You are NOT allowed to infer, assume, or add information.
You must ONLY use the provided Question and Chat history.

DEFINITIONS:

A message is considered a VALID HANDLING if it satisfies AT LEAST ONE of the following:

   A. DIRECT ANSWER
      - Directly resolves the question
      - Provides guidance, explanation, or solution
      - Confirms the task is being handled (e.g., "để em xem", "đang xử lý")
      - Confirms inability or delay with a reason (e.g., "chưa làm được vì...", "đang bận")
      - Semantically answers the user's request, even if answered by a third party

   B. CLARIFYING QUESTION
      - Asks for more information in order to handle the question
      - Is logically related to the question
      - Examples:
        - "Bạn gặp khó khăn gì?"
        - "Lỗi xảy ra khi nào?"
        - "Đây là code hả?"

   C. DELEGATION / REDIRECTION
      - Explicitly forwards or assigns the question to another person or team
      - Examples:
        - "nhờ anh @X xử lý"
        - "chuyển cho team Y nhé"
        - "anh @Z có thể giúp việc này"

   D. SCHEDULED HANDLING
      - Commits to handling the question at a specific later time
      - Examples:
        - "để mai anh xử lý"
        - "chiều nay em làm"
        - "chờ anh chút"

   E. MEANINGFUL ACKNOWLEDGEMENT
      - A short but clearly intentional acknowledgement that signals the question
        has been received and will be handled
      - Includes: "ok", "được", "hiểu rồi", thumbs-up emoji (👍), check emoji (✅)
      - Must appear in direct reply to the question or immediately after it
        in the conversation flow


EXCLUSION RULES:
- A message is NOT a VALID HANDLING if:
  1. It is the original question itself or a restatement of it
  2. It is sent by the same person who asked the question
     (use the "sender_name" field to identify the sender)
  3. It is completely unrelated to the question (off-topic, side conversation)
  4. It only repeats or quotes the question without adding new information
  5. It is a meaningless reaction (random emojis, stickers with no acknowledgement intent)
  6. It is a deleted message placeholder (e.g., "[tin nhắn đã bị xóa]")
  7. It is a response that clearly misunderstands the question and addresses
     a completely different topic
  8. It is an ambiguous one-word reply (e.g., "ok", "được") that appears
     in a different conversation thread unrelated to the question


PARTIAL HANDLING RULES:
- If the question contains multiple sub-questions:
  - A message that answers AT LEAST ONE sub-question is considered VALID
- If the answer only partially addresses the question but shows clear
  intent to handle it, it is considered VALID


FAST-PATH RULE (check this FIRST, before anything else):
- If ANY message in the chat history has role "admin" or "bot",
  immediately return true. The question is already being handled.
  Do NOT analyze further.


INSTRUCTIONS:
- Each message in the chat history has: "id" (platform message ID),
  "role" (customer/admin/bot), "sender_name" (name of the sender),
  "content", and "datetime".
- The "Question" provided above is the EXACT question you must evaluate.
  Do NOT evaluate any other questions found in the chat history.
- SCOPE: Only consider messages that appear AFTER the question
  in chronological order (by datetime). Messages that appear BEFORE
  the question are old context and must be IGNORED entirely.
- Identify the person who asked the question using sender_name AND role.
- Ignore all messages sent by that same sender_name with the same role.
- Compare the question with EACH remaining in-scope message.
- Apply EXCLUSION RULES first to filter out invalid messages.
- Then check if any remaining message satisfies at least one condition (A to E).
- If ANY message qualifies as a VALID HANDLING, return true.
- If NONE qualify, return false with the "id" of the customer message
  that most needs support.

OUTPUT:
Return ONLY one of the following formats:
- true
- false|<id>
  where <id> is the "id" of the customer message that most needs support.
  If the question spans multiple messages, use the "id" of the FIRST question message.

Do NOT explain.
Do NOT add text."""

        user_content = f"""Question:
{question}

Chat history:
{history_chat}"""

        response = client.chat.completions.create(
            model="ep-20260306171113-dqqlf",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.0,
        )

        output_text = response.choices[0].message.content.strip()
        output_lower = output_text.lower()

        if "true" in output_lower:
            output_val = "true"
            reply_msg_id = None
        else:
            output_val = "false"
            # Extract message ID from format "false|<id>"
            parts = output_text.split("|", 1)
            reply_msg_id = parts[1].strip() if len(parts) > 1 else None

        class _DummyResponse:
            def json(self):
                resp = {"output": output_val}
                if reply_msg_id:
                    resp["reply_to_msg_id"] = reply_msg_id
                return resp

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
Determine whether the following input (which may be multiple messages
concatenated with newlines from the same user within a short time window)
contains a QUESTION or REQUEST that expects a response, help, or action.


RETURN TRUE if the message:

   A. EXPLICIT QUESTION
      - Contains a direct question (with or without a question mark)
      - Examples:
        - "lỗi này fix thế nào?"
        - "sao hệ thống chậm vậy"
        - "đã xong chưa"

   B. PROBLEM / ERROR REPORT
      - Reports a bug, error, incident, or abnormal situation
      - Implies that help or investigation is needed
      - Examples:
        - "hệ thống đang bị lỗi"
        - "em vừa deploy xong mà user vẫn báo lỗi"
        - "không vào được trang chủ"

   C. IMPLICIT QUESTION
      - Does not ask directly but clearly implies a need for explanation,
        confirmation, or help
      - Examples:
        - "không biết sao hôm nay hệ thống chậm thế"
        - "trời ơi sao lại thế này???"
        - "cái này kỳ lạ thật"

   D. EXPLICIT REQUEST / COMMAND
      - Asks someone to do something or provide something
      - May or may not include a question mark
      - Examples:
        - "check giúp anh"
        - "xem lại cái này"
        - "anh xử lý giúp em với"
        - "cần support gấp"

   E. CONFIRMATION REQUEST
      - Asks to verify or confirm a fact, status, or action
      - Examples:
        - "anh xử lý rồi đúng không?"
        - "đã done chưa?"
        - "merge rồi phải không?"

   F. MIXED MESSAGE (notify + ask)
      - Contains at least one part that qualifies as A–E above,
        even if other parts are pure statements
      - Examples:
        - "em đã thử cách đó rồi nhưng vẫn không được, giờ làm sao?"
        - "deploy xong rồi, anh kiểm tra giúp em nhé"

   G. TAG + CONTENT REQUIRING ACTION
      - Tags a person or group AND includes content that requires a response or action
      - Examples:
        - "@admin hệ thống đang lỗi"
        - "@team check giúp với"

   H. MEDIA WITH CONTEXT
      - A message containing "[image]" or "[file]" that is accompanied by
        a question or request in the same batch → TRUE
      - But "[image]" or "[file]" ALONE with no question/request text → FALSE


RETURN FALSE if the messages:

   A. GREETING / FAREWELL
      - "xin chào", "hi", "bye", "good morning"

   B. PURE ACKNOWLEDGEMENT
      - "ok", "được", "hiểu rồi", "noted", "👍", "✅"
      - Does not accompany any question or request

   C. PURE STATEMENT / ANNOUNCEMENT
      - Shares information with no expectation of response or action
      - Examples:
        - "em đã fix xong rồi nhé"
        - "deploy lúc 3h chiều"
        - "meeting dời sang thứ 4"

   D. RHETORICAL QUESTION / TALKING TO SELF
      - Phrased as a question but clearly not directed at anyone
        and does not expect an answer
      - Examples:
        - "sao cái này khó thế không biết"
        - "ôi trời, tại sao mình lại quên nhỉ"

   E. POLITE CONVERSATIONALISM
      - Small talk or social pleasantries with no request embedded
      - Examples:
        - "cảm ơn anh nhiều nhé"
        - "chúc anh cuối tuần vui vẻ"

   F. TAG + PURE ACKNOWLEDGEMENT
      - Tags someone but content is only an acknowledgement, not a request
      - Examples:
        - "@admin ok nhé"
        - "@team noted rồi"


AMBIGUITY RULES:
- If the message could belong to both TRUE and FALSE categories,
  lean toward TRUE (assume the sender expects a response).
- Short emotional expressions (e.g., "???", "!!!") combined with
  context suggesting a problem → TRUE.
- Colloquial or abbreviated language (e.g., "lỗi r", "fix sao ta",
  "sao vậy ta") should still be classified correctly based on intent.


OUTPUT:
Return ONLY:
- true
- false

Do NOT explain.
Do NOT add text."""

        response = client.chat.completions.create(
            # Specify the Ark Inference Point ID that you created, which has been changed for you here to your Endpoint ID
            model="ep-20260306171113-dqqlf",
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"Messages (may contain multiple messages separated by newlines):\n\n{content}",
                },
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


_MESSAGE_TYPE_MARKER = {
    "image": "[image]",
    "file": "[file]",
}


def build_history_chat(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Build history chat format for agent payload.

    Args:
        history: List of message history

    Returns:
        Formatted history list. Non-text messages get a `[image]` or `[file]`
        marker prepended to content so the agent is aware of attachments
        without needing the raw URL.
    """
    result: List[Dict[str, Any]] = []
    for msg in history:
        content = msg.get("content") or ""
        message_type = msg.get("message_type")

        marker = _MESSAGE_TYPE_MARKER.get(message_type)
        if marker:
            content = f"{marker} {content}".strip()

        result.append(
            {
                "id": msg.get("platform_msg_id", ""),
                "role": msg.get("sender_type"),
                "sender_name": msg.get("sender_name", ""),
                "content": content,
                "datetime": msg.get("datetime"),
            }
        )
    return result
