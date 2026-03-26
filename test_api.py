import requests
import json
import time

BASE_URL = "http://localhost:8000/api"
TEST_TELEGRAM_GROUP = "-5236384276"
TEST_TELEGRAM_TOKEN = "8685270318:AAFZaanLwJNyX3K3ilgc5b-vWQgeCx71e1I"

def test_api():
    print("--- Starting API Tests ---")
    
    # 1. Create a bot
    bot_id = "test_bot_1"
    create_data = {
        "botId": bot_id,
        "options": {
            "platform": "telegram",
            "token": TEST_TELEGRAM_TOKEN  # Placeholder token
        }
    }
    print(f"Creating bot {bot_id}...")
    try:
        response = requests.post(f"{BASE_URL}/bots", json=create_data)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
    except Exception as e:
        print(f"Failed to create bot: {e}")
    
    # 2. Get status
    print(f"\nGetting status for {bot_id}...")
    try:
        response = requests.get(f"{BASE_URL}/bots/{bot_id}/status")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
    except Exception as e:
        print(f"Failed to get status: {e}")
        
    # 3. List bots in Redis (simulating a check)
    # This requires reaching into Redis, but we'll just check the API response for now.
    
    # 4. Delete the bot
    print(f"\nDeleting bot {bot_id}...")
    try:
        response = requests.delete(f"{BASE_URL}/bots/{bot_id}")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
    except Exception as e:
        print(f"Failed to delete bot: {e}")

if __name__ == "__main__":
    test_api()
