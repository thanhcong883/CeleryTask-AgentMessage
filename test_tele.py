import requests
import pytest
import time

def test_telegram_bot_lifecycle(server_process, worker_process, tunnel_url, test_env, request_with_retry):
    BASE_URL = f"{tunnel_url}/api"
    bot_id = "pytest_tg_bot"
    token = test_env["token"]

    if not token:
        pytest.fail("TEST_TELEGRAM_TOKEN not found in .env.test")

    # 1. Create Bot
    create_payload = {
        "botId": bot_id,
        "options": {
            "platform": "telegram",
            "token": token
        }
    }
    response = request_with_retry("POST", f"{BASE_URL}/bots", json=create_payload)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    # 2. Check Status
    # In webhook mode, status is "up" if the webhook is correctly set to our tunnel URL
    time.sleep(2)
    response = request_with_retry("GET", f"{BASE_URL}/bots/{bot_id}/status")
    assert response.status_code == 200
    data = response.json()
    print(data)
    assert data["platform"] == "telegram"
    # Status should be "up" if setWebhook call succeeded during creation
    assert data["status"] == "up"

    # 3. Delete Bot
    response = request_with_retry("DELETE", f"{BASE_URL}/bots/{bot_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    # Verify it's gone
    response = request_with_retry("GET", f"{BASE_URL}/bots/{bot_id}/status")
    assert response.status_code == 404

def test_manual_message_receipt(server_process, worker_process, tunnel_url, test_env, request_with_retry):
    """
    Test that the bot can receive a manual message from a real user via Webhook.
    This test waits for 5 minutes for a message to arrive in the group.
    """
    BASE_URL = f"{tunnel_url}/api"
    import redis
    import json
    import config

    bot_id = "pytest_manual_bot"
    token = test_env["token"]
    group_id = test_env["group_id"]

    if not token or not group_id:
        pytest.fail("TEST_TELEGRAM_TOKEN or TEST_TELEGRAM_GROUP not found in .env.test")

    # 1. Create Bot (automatically sets webhook to tunnel_url)
    create_payload = {
        "botId": bot_id,
        "options": {"platform": "telegram", "token": token}
    }
    response = request_with_retry("POST", f"{BASE_URL}/bots", json=create_payload)
    assert response.status_code == 200

    # 2. Wait for Webhook initialization and send an invitation message
    time.sleep(5)
    import uuid
    random_text = f"TEST-{uuid.uuid4().hex[:8]}"

    send_payload = {
        "content": f"TEST START: Please send the following exact text to this group within 5 minutes:\n\n{random_text}",
        "group_id": group_id,
        "type": "group"
    }
    request_with_retry("POST", f"{BASE_URL}/bots/{bot_id}/send", json=send_payload)

    # 3. Wait 5 minutes for user message
    print(f"\n>>> PLEASE SEND THIS TEXT TO THE TELEGRAM GROUP: {random_text}")
    print(">>> WAITING 5 MINUTES...")

    received = False
    start_time = time.time()
    timeout = 300 # 5 minutes

    while time.time() - start_time < timeout:
        # Check /api/messages endpoint (which returns messages stored in Redis)
        try:
            resp = request_with_retry("GET", f"{BASE_URL}/messages")
            if resp.status_code == 200:
                messages = resp.json().get("messages", [])
                for msg in messages:
                    if msg.get("content") == random_text and str(msg.get("platform_conv_id")) == str(group_id):
                        print(f"\n>>> SUCCESS! Received match: {msg['content']}")
                        received = True
                        break
        except Exception as e:
            print(f"Error polling /api/messages: {e}")

        if received:
            break
        time.sleep(5)

    # Cleanup
    request_with_retry("DELETE", f"{BASE_URL}/bots/{bot_id}")

    assert received, f"Did not receive the expected text '{random_text}' in the group within 5 minutes."
