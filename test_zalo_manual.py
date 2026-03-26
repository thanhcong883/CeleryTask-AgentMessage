import requests
import pytest
import time
import uuid
import os

BASE_URL = "http://localhost:8000/api"

def test_zalo_manual_message_receipt(server_process, worker_process, test_env):
    """
    Test that the system can receive a manual message from a real user via Zalo.
    This test generates a random code and waits for the user to send it to the Zalo OA.
    """
    # Use 'kien' as the default bot ID if not provided in environment
    bot_id = test_env.get("zalo_bot_id", "kien")
    group_id = test_env.get("zalo_group_id") or "3739163992970418355"
    
    # 1. Generate a unique random text
    random_text = f"TEST-ZALO-{uuid.uuid4().hex[:8]}"
    
    # 2. Identify target (Group or User)
    if group_id:
        target_id = group_id
        msg_type = "group"
        target_desc = f"ZALO GROUP (ID: {group_id})"
    else:
        # Fallback to asking user directly if no group is provided
        target_id = None
        msg_type = "private"
        target_desc = f"ZALO BOT (ID: {bot_id})"

    # 3. Inform the user and send invitation if group is available
    print(f"\n>>> PLEASE SEND THE FOLLOWING TEXT TO {target_desc} using Bot {bot_id}:")
    print(f"\n    {random_text}\n")
    
    if target_id:
        send_payload = {
            "content": f"TEST START: Please reply with the following exact text to this group within 5 minutes:\n\n{random_text}",
            "group_id": target_id,
            "type": msg_type
        }
        resp = requests.post(f"{BASE_URL}/bots/{bot_id}/send", json=send_payload)
        if resp.status_code != 200:
            print(f"Warning: Failed to send initial invitation: {resp.text}")

    print(">>> WAITING 5 MINUTES FOR RECEIPT...")
    
    received = False
    start_time = time.time()
    timeout = 300 # 5 minutes
    
    while time.time() - start_time < timeout:
        try:
            # Poll /api/messages endpoint
            response = requests.get(f"{BASE_URL}/messages")
            if response.status_code == 200:
                messages = response.json().get("messages", [])
                for msg in messages:
                    # Check if platform is Zalo and content matches
                    # Also check conv_id if it's a group test
                    if msg.get("platform_name") == "Zalo" and msg.get("content") == random_text:
                        if not group_id or str(msg.get("platform_conv_id")) == str(group_id):
                            print(f"\n>>> SUCCESS! Received match from Zalo: {msg['content']}")
                            received = True
                            break
            else:
                print(f"Error polling /api/messages: {response.text}")
        except Exception as e:
            print(f"Connection error: {e}")
            
        if received:
            break
        time.sleep(5)
        
    assert received, f"Did not receive the expected text '{random_text}' from Zalo within 5 minutes."
