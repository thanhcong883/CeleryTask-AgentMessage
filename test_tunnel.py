import requests
import time
import logging
import pytest

def test_get_bots_via_tunnel(tunnel_url):
    """
    Verifies that the list of bots can be retrieved via the public tunnel URL.
    Uses retries to handle potential DNS propagation delays.
    """
    # Wait a moment for the tunnel to be fully established and stable
    time.sleep(5)
    
    url = f"{tunnel_url}/api/bots"
    print(f"\n>>> Requesting: {url}")
    
    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=10)
            print(f">>> Attempt {attempt + 1}: Status Code: {response.status_code}")
            
            if response.status_code == 200:
                print(f">>> Response: {response.json()}")
                data = response.json()
                assert data["status"] == "ok"
                assert "bots" in data
                assert isinstance(data["bots"], list)
                return # Success!
            
            print(f">>> Unexpected status code: {response.status_code}. Retrying...")
            
        except (requests.exceptions.RequestException, requests.exceptions.ConnectionError) as e:
            print(f">>> Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                print(">>> Retrying in 5 seconds...")
                time.sleep(5)
            else:
                pytest.fail(f"Request to tunnel URL failed after {max_retries} attempts: {e}")

if __name__ == "__main__":
    # This block allows running the test script directly if needed,
    # though it's designed to be run with pytest to use the fixtures.
    pytest.main([__file__, "-s"])
