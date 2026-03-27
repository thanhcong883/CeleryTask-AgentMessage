import requests
import pytest
import time

def test_zalo_bot_lifecycle(server_process, worker_process, tunnel_url, test_env, request_with_retry):
    """
    Test the lifecycle of a Zalo bot: Create -> Status -> QR Code -> Delete.
    """
    BASE_URL = f"{tunnel_url}/api"
    bot_id = "pytest_zalo_bot"
    
    try:
        # 1. Create Bot
        create_payload = {
            "botId": bot_id,
            "options": {
                "platform": "zalo"
            }
        }
        response = request_with_retry("post", f"{BASE_URL}/bots", json=create_payload)
        print(f"\n>>> Create Bot Response: {response.status_code} - {response.text}")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

        # 2. Check Status
        # Give it a moment for the external API call
        time.sleep(2)
        response = request_with_retry("get", f"{BASE_URL}/bots/{bot_id}/status")
        assert response.status_code == 200
        data = response.json()
        assert data["platform"] == "zalo"
        # Status depends on the external API but should return something
        assert "status" in data

        # 3. Check QR Code
        time.sleep(15)
        response = request_with_retry("get", f"{BASE_URL}/bots/{bot_id}/qrcode.png")
        assert response.status_code == 200
        assert response.headers["Content-Type"] == "image/png"
        assert len(response.content) > 0
    finally:
        # 4. Delete Bot - Always run cleanup
        response = request_with_retry("delete", f"{BASE_URL}/bots/{bot_id}")
        print(f">>> Cleanup Delete Bot Response: {response.status_code}")
        
        if response.status_code == 200:
            assert response.json()["status"] == "ok"
            # Verify it's gone
            response = request_with_retry("get", f"{BASE_URL}/bots/{bot_id}/status")
            assert response.status_code == 404
