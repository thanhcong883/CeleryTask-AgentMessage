import requests
import pytest
import time

BASE_URL = "http://localhost:8000/api"

def test_zalo_bot_lifecycle(server_process, worker_process, mock_zalo_server, test_env):
    """
    Test the lifecycle of a Zalo bot: Create -> Status -> QR Code -> Delete.
    """
    bot_id = "pytest_zalo_bot"
    
    # 1. Create Bot
    create_payload = {
        "botId": bot_id,
        "options": {
            "platform": "zalo"
        }
    }
    response = requests.post(f"{BASE_URL}/bots", json=create_payload)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    # 2. Check Status
    # Give it a moment for the external API call
    time.sleep(2)
    response = requests.get(f"{BASE_URL}/bots/{bot_id}/status")
    assert response.status_code == 200
    data = response.json()
    assert data["platform"] == "zalo"
    # Status depends on the external API but should return something
    assert "status" in data

    # 3. Check QR Code
    response = requests.get(f"{BASE_URL}/bots/{bot_id}/qrcode.png")
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "image/png"
    assert len(response.content) > 0

    # 4. Delete Bot
    response = requests.delete(f"{BASE_URL}/bots/{bot_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    
    # Verify it's gone
    response = requests.get(f"{BASE_URL}/bots/{bot_id}/status")
    assert response.status_code == 404
