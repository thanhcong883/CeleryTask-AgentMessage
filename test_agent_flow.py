import pytest
import json
from unittest.mock import patch, MagicMock
from tasks import (
    process_message,
    task_check_question,
    check_agent_answer,
    _get_cached_conversation_info,
    _get_cached_conversation_members
)

# Dummy test data
dummy_conversation_id = "test_conv_123"
dummy_message_id = "test_msg_456"

dummy_conv_info = {
    "use_agent": True,
    "group_admin": False,
    "type": "group",
    "time_to_use_agent": 300,
    "platform_conv_id": "platform_group_1",
    "bot_message": "Bot is here",
    "title": "Test Group",
    "bot_sent_to": []
}

dummy_members = [
    {
        "customer": {"platform_user_id": "test_user_789"},
        "role_app": "customer"
    }
]

dummy_msg_data = {
    "platform_name": "Telegram",
    "content": "Hello shop",
    "platform_user_id": "test_user_789",
    "platform_conv_id": "platform_group_1"
}

@patch("tasks.redis_client")
@patch("tasks.get_conversation_info")
def test_cache_conversation_info_miss_then_hit(mock_get_info, mock_redis):
    # Setup mock to simulate a cache miss first, then hit
    mock_redis.get.side_effect = [None, json.dumps(dummy_conv_info)]
    mock_get_info.return_value = dummy_conv_info

    # First call - cache miss, should hit API
    info1 = _get_cached_conversation_info(dummy_conversation_id)
    assert info1 == dummy_conv_info
    mock_get_info.assert_called_once_with(dummy_conversation_id)
    mock_redis.setex.assert_called_once()

    # Reset mock API call count
    mock_get_info.reset_mock()

    # Second call - cache hit, API should not be called
    info2 = _get_cached_conversation_info(dummy_conversation_id)
    assert info2 == dummy_conv_info
    mock_get_info.assert_not_called()

@patch("tasks.redis_client")
@patch("tasks.get_conversation_members")
def test_cache_conversation_members(mock_get_members, mock_redis):
    mock_redis.get.return_value = None
    mock_get_members.return_value = dummy_members

    members = _get_cached_conversation_members(dummy_conversation_id)
    assert members == dummy_members
    mock_get_members.assert_called_once_with(dummy_conversation_id)
    mock_redis.setex.assert_called_once()

@patch("tasks.sync_message")
@patch("tasks._get_cached_conversation_info")
@patch("tasks._get_cached_conversation_members")
@patch("tasks.redis_client")
@patch("tasks.task_check_question.apply_async")
def test_process_message_debounce_scheduling(
    mock_apply_async, mock_redis, mock_cached_members, mock_cached_info, mock_sync
):
    # Setup mocks
    mock_sync_resp = MagicMock()
    mock_sync_resp.json.return_value = {"data": [{"data": {"conversationId": dummy_conversation_id, "messageId": dummy_message_id}}]}
    mock_sync.return_value = mock_sync_resp
    mock_cached_info.return_value = dummy_conv_info
    mock_cached_members.return_value = dummy_members
    mock_redis.get.return_value = None # No admin active

    # Call process_message
    process_message(dummy_msg_data)

    # Assert latest user message is set
    mock_redis.setex.assert_called_with(f"latest_user_message:{dummy_conversation_id}", 3600, dummy_message_id)

    # Assert task_check_question is scheduled with 60s countdown
    mock_apply_async.assert_called_once()
    args, kwargs = mock_apply_async.call_args
    assert kwargs.get("countdown") == 60
    assert kwargs.get("args")[1] == dummy_conversation_id # Extracting args tuple sent to task

@patch("tasks.redis_client")
@patch("tasks.get_message_history")
@patch("tasks.check_question")
@patch("tasks.check_agent_answer.apply_async")
def test_task_check_question_debounce_failure(
    mock_apply_async, mock_check_q, mock_history, mock_redis
):
    # Setup mock to simulate a NEWER message exists in Redis
    mock_redis.get.return_value = "newer_msg_999"

    # Call the task with an older message ID
    task_check_question(dummy_msg_data, dummy_conversation_id, dummy_message_id, dummy_conv_info)

    # Assert history and check_question APIs are NOT called (debounced)
    mock_history.assert_not_called()
    mock_check_q.assert_not_called()
    mock_apply_async.assert_not_called()

@patch("tasks.redis_client")
@patch("tasks.get_message_history")
@patch("tasks.check_question")
@patch("tasks.check_agent_answer.apply_async")
def test_task_check_question_success_combines_text(
    mock_apply_async, mock_check_q, mock_history, mock_redis
):
    # Setup mock to simulate this IS the latest message
    mock_redis.get.return_value = dummy_message_id

    # Setup history with 3 recent customer messages (oldest to newest is how get_message_history usually works in standard order)
    mock_history.return_value = [
        {"sender_type": "bot", "content": "Can I help you?"}, # Older
        {"sender_type": "customer", "content": "Hello shop."},
        {"sender_type": "customer", "content": "Color red?"},
        {"sender_type": "customer", "content": "Price?"} # Newest
    ]

    mock_check_resp = MagicMock()
    mock_check_resp.json.return_value = {"output": "true"}
    mock_check_q.return_value = mock_check_resp

    # Call task
    task_check_question(dummy_msg_data, dummy_conversation_id, dummy_message_id, dummy_conv_info)

    # Assert check_question called with COMBINED text
    mock_check_q.assert_called_once_with("Hello shop. Color red? Price?")

    # Assert latest_question_message is updated
    mock_redis.setex.assert_called_with(f"latest_question_message:{dummy_conversation_id}", 3600, dummy_message_id)

    # Assert agent check is scheduled
    mock_apply_async.assert_called_once()
    args, kwargs = mock_apply_async.call_args
    assert kwargs.get("countdown") == 300 # time_to_use_agent

@patch("tasks.redis_client")
@patch("tasks.get_message_history")
@patch("tasks.call_agent_webhook")
def test_check_agent_answer_debounce_failure(
    mock_webhook, mock_history, mock_redis
):
    # Setup mock: redis indicates a NEWER question is scheduled
    mock_redis.get.side_effect = ["newer_question_999", None] # First for debounce check, second for bot processing lock

    # Call task
    check_agent_answer({"conversation": dummy_conversation_id, "message_id": dummy_message_id})

    # Assert history and webhook NOT called (debounced)
    mock_history.assert_not_called()
    mock_webhook.assert_not_called()
