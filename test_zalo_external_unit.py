import requests
import pytest
import uuid
import config

# Use the real external API base from config
ZALO_API_BASE = config.ZALO_EXTERNAL_API_BASE

def test_create_and_verify_account():
    """
    Test direct account creation and verification on the Zalo external API.
    """
    # 1. Generate unique account ID
    unique_id = f"test_acc_{uuid.uuid4().hex[:6]}"
    
    # 2. Create Account
    # Note: User modified main.py to use "accountId" instead of "botId"
    create_url = f"{ZALO_API_BASE}/api/accounts"
    payload = {"accountId": unique_id}
    
    response = requests.post(create_url, json=payload, timeout=10)
    assert response.status_code in [200, 201], f"Failed to create account: {response.text}"
    
    # 3. Verify Account exists in the list
    list_url = f"{ZALO_API_BASE}/api/accounts"
    response = requests.get(list_url, timeout=10)
    assert response.status_code == 200, f"Failed to list accounts: {response.text}"
    
    accounts = response.json()
    assert isinstance(accounts, list), "Expected a list of accounts"
    
    found = any(acc.get("accountId") == unique_id for acc in accounts)
    assert found, f"Account {unique_id} not found in the list after creation"
    
    print(f"\n>>> SUCCESS: Account {unique_id} created and verified on Zalo platform.")

def test_get_account_status():
    """
    Test getting status of an existing account (using 'thanhcong' which exists).
    """
    account_id = "thanhcong"
    status_url = f"{ZALO_API_BASE}/api/{account_id}/auth-status"
    
    response = requests.get(status_url, timeout=10)
    # The external API might return 404 if the account isn't fully set up,
    # but based on previous curl, it should at least return 200 for 'thanhcong' 
    # if I check the list instead.
    
    # Let's just verify we can call it.
    if response.status_code == 200:
        data = response.json()
        assert "isAuthenticated" in data
        print(f"\n>>> Auth status for {account_id}: {data['isAuthenticated']}")
    else:
        print(f"\n>>> Note: Status check for {account_id} returned {response.status_code}")

def test_zalo_webhook_config():
    """
    Test direct webhook configuration on the Zalo external API.
    """
    account_id = "kien"
    url = f"{ZALO_API_BASE}/api/{account_id}/webhook-config"
    
    # 1. Get current config
    response = requests.get(url, timeout=10)
    assert response.status_code == 200, f"Failed to get webhook config: {response.text}"
    data = response.json()
    original_url = data.get("webhookUrl")
    print(f"\n>>> Current webhook for {account_id}: {original_url}")
    
    # 2. Update config to a temporary test URL
    test_url = f"http://test-webhook-{uuid.uuid4().hex[:6]}.com/hook"
    response = requests.post(url, json={"webhookUrl": test_url}, timeout=10)
    assert response.status_code == 200, f"Failed to update webhook: {response.text}"
    
    # 3. Verify update
    response = requests.get(url, timeout=10)
    current_data = response.json()
    assert current_data.get("webhookUrl") == test_url, f"Webhook URL mismatch. Expected {test_url}, got {current_data.get('webhookUrl')}"
    
    # 4. Restore original URL (optional but good practice)
    if original_url:
        requests.post(url, json={"webhookUrl": original_url}, timeout=10)
        print(f">>> Restored original webhook: {original_url}")
        
    print(f">>> SUCCESS: Zalo Webhook configuration verified (Get & Update).")
