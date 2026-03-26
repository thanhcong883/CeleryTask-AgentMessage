import requests
import os
import uuid

# Use localhost:8000 since server is started by conftest or manually
BASE_URL = "http://123.30.233.74:5000/api"

def test_send():
    # Attempt to load from environment or use kien/TEST_ZALO_GROUP as suggested
    bot_id = os.getenv("TEST_ZALO_BOT_ID", "kien")
    group_id = os.getenv("TEST_ZALO_GROUP", "3739163992970418355")
    
    print(f"Testing Zalo Send API for Bot: {bot_id}, Group: {group_id}")
    
    payload = {
        "text": f"Manual test message {uuid.uuid4().hex[:6]}",
        "threadId": group_id,
        "type": "group"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/{bot_id}/send", json=payload, timeout=10)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        if response.status_code == 200:
            print(">>> Send API call succeeded at the platform level.")
        else:
            print(">>> Send API call failed.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_send()
