import requests
import pytest
import time

BASE_URL = "http://localhost:8000/api"

def test_telegram_bot_lifecycle(server_process, worker_process, test_env):
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
    response = requests.post(f"{BASE_URL}/bots", json=create_payload)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    # 2. Check Status
    # Give it a moment to initialize the bot thread
    time.sleep(2)
    response = requests.get(f"{BASE_URL}/bots/{bot_id}/status")
    assert response.status_code == 200
    data = response.json()
    assert data["platform"] == "telegram"
    # Status should be "wait" or "up" initially. 
    # If the token is valid, it might eventually become "up".
    assert data["status"] in ["wait", "up"]

    # 3. Delete Bot
    response = requests.delete(f"{BASE_URL}/bots/{bot_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    
    # Verify it's gone
    response = requests.get(f"{BASE_URL}/bots/{bot_id}/status")
    assert response.status_code == 404

def test_manual_message_receipt(server_process, worker_process, test_env):
    """
    Test that the bot can receive a manual message from a real user.
    This test waits for 5 minutes for a message to arrive in the group.
    """
    import redis
    import json
    import config
    
    bot_id = "pytest_manual_bot"
    token = test_env["token"]
    group_id = test_env["group_id"]
    
    if not token or not group_id:
        pytest.fail("TEST_TELEGRAM_TOKEN or TEST_TELEGRAM_GROUP not found in .env.test")

    # Clear Redis test list indirectly or just rely on the unique random string
    # (The /api/messages returns all messages from the last 10 mins)

    # 1. Create Bot
    create_payload = {
        "botId": bot_id,
        "options": {"platform": "telegram", "token": token}
    }
    response = requests.post(f"{BASE_URL}/bots", json=create_payload)
    assert response.status_code == 200

    # 2. Wait for Bot to initialize and send an invitation message
    time.sleep(5)
    import uuid
    random_text = f"TEST-{uuid.uuid4().hex[:8]}"
    
    send_payload = {
        "content": f"TEST START: Please send the following exact text to this group within 5 minutes:\n\n{random_text}",
        "group_id": group_id,
        "type": "group"
    }
    requests.post(f"{BASE_URL}/bots/{bot_id}/send", json=send_payload)

    # 3. Wait 5 minutes for user message
    print(f"\n>>> PLEASE SEND THIS TEXT TO THE TELEGRAM GROUP: {random_text}")
    print(">>> WAITING 5 MINUTES...")
    
    received = False
    start_time = time.time()
    timeout = 300 # 5 minutes
    
    while time.time() - start_time < timeout:
        # Check /api/messages endpoint
        try:
            resp = requests.get(f"{BASE_URL}/messages")
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
    requests.delete(f"{BASE_URL}/bots/{bot_id}")
    
    assert received, f"Did not receive the expected text '{random_text}' in the group within 5 minutes."
