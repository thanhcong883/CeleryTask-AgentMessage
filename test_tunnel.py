import requests
import time
import logging

def test_get_bots_via_tunnel(tunnel_url):
    """
    Verifies that the list of bots can be retrieved via the public tunnel URL.
    """
    # Wait a moment for the tunnel to be fully established and stable
    time.sleep(2)
    
    url = f"{tunnel_url}/api/bots"
    print(f"\n>>> Requesting: {url}")
    
    try:
        response = requests.get(url, timeout=10)
        print(f">>> Status Code: {response.status_code}")
        print(f">>> Response: {response.json()}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "bots" in data
        assert isinstance(data["bots"], list)
        
    except requests.exceptions.RequestException as e:
        pytest.fail(f"Request to tunnel URL failed: {e}")

if __name__ == "__main__":
    # This block allows running the test script directly if needed,
    # though it's designed to be run with pytest to use the fixtures.
    import pytest
    pytest.main([__file__, "-s"])
