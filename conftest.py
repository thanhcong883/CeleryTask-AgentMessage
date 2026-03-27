import pytest
import subprocess
import time
import requests
import os
import signal
import re

@pytest.fixture(scope="session")
def tunnel_url(server_process):
    """Starts a cloudflared tunnel and returns the public URL."""
    # cloudflared MUST run after server started to verify local port 8000
    cmd = ["cloudflared", "tunnel", "--url", "http://localhost:8000"]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, preexec_fn=os.setsid)
    
    url = None
    max_retries = 30
    import re
    # Pattern to match: https://*.trycloudflare.com
    url_pattern = re.compile(r"https://[a-zA-Z0-9\.-]+\.trycloudflare\.com")
    
    for _ in range(max_retries):
        line = process.stdout.readline()
        if not line:
            break
        match = url_pattern.search(line)
        if match:
            url = match.group(0)
            break
        time.sleep(1)
    
    if not url:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        raise RuntimeError("Failed to get cloudflared tunnel URL")
    
    print(f"\n>>> TUNNEL GENERATED: {url}")
    
    # Wait for the tunnel to be reachable and stable (DNS propagation)
    print(">>> WAITING FOR TUNNEL STABILITY (5 consecutive successful pings to /docs)...")
    success_count = 0
    for _ in range(60):
        try:
            # Ping /docs to ensure the FastAPI app is actually reachable
            resp = requests.get(f"{url}/docs", timeout=5)
            if resp.status_code == 200:
                success_count += 1
                print(f">>> Ping {success_count}/5 successful...")
                if success_count >= 5:
                    break
                time.sleep(1) # Small delay between pings
            else:
                success_count = 0
                time.sleep(2)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.HTTPError):
            success_count = 0
            time.sleep(2)
    
    if success_count < 5:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        raise RuntimeError(f"Cloudflared tunnel {url} not stable after 120 seconds")
    
    print(f">>> TUNNEL READY AND STABLE: {url}")
    # Final grace period
    time.sleep(2)
    
    # Update the server's BASE_URL dynamically via the new config endpoint
    try:
        requests.post("http://localhost:8000/api/config", json={"BASE_URL": url}, timeout=5)
        print(f">>> Server BASE_URL updated to {url}")
    except Exception as e:
        print(f"!!! Failed to update server BASE_URL: {e}")
    
    yield url
    
    # Teardown
    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    process.wait()

@pytest.fixture(scope="session")
def server_process(test_env):
    """Starts the FastAPI server for the duration of the test session."""
    cmd = ["python3", "main.py"]
    env = os.environ.copy()
    # BASE_URL is localhost, will be updated by tunnel_url fixture
    env["BASE_URL"] = "http://localhost:8000"
    # Ensure all test env vars are present
    if "ZALO_EXTERNAL_API_BASE" in os.environ:
        env["ZALO_EXTERNAL_API_BASE"] = os.environ["ZALO_EXTERNAL_API_BASE"]
    log_file = open("server_test.log", "w")
    process = subprocess.Popen(cmd, stdout=log_file, stderr=log_file, env=env, preexec_fn=os.setsid)
    
    # Wait for server to be ready
    max_retries = 10
    for i in range(max_retries):
        try:
            response = requests.get("http://localhost:8000/docs", timeout=1)
            if response.status_code == 200:
                break
        except requests.exceptions.ConnectionError:
            time.sleep(1)
    else:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        raise RuntimeError("Server failed to start")
        
    yield process
    
    # Teardown: terminate the server and its subprocesses
    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    process.wait()

@pytest.fixture(scope="session")
def worker_process(test_env):
    """Starts the Celery worker for the duration of the test session."""
    cmd = ["celery", "-A", "tasks", "worker", "--loglevel=info", "-Q", "celery_receive_message,celery_send_message,celery_agent_message", "--concurrency=1"]
    log_file = open("worker_test.log", "w")
    env = os.environ.copy()
    process = subprocess.Popen(cmd, stdout=log_file, stderr=log_file, env=env, preexec_fn=os.setsid)
    
    # Give it some time to start
    time.sleep(3)
    
    yield process
    
    # Teardown: terminate the worker and its subprocesses
    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    process.wait()

@pytest.fixture(scope="session")
def test_env():
    """Loads environment variables from .env.test."""
    from dotenv import load_dotenv
    load_dotenv(".env")
    load_dotenv(".env.test", override=True)
    return {
        "token": os.getenv("TEST_TELEGRAM_TOKEN"),
        "token_2": os.getenv("TEST_TELEGRAM_TOKEN_2"),
        "group_id": os.getenv("TEST_TELEGRAM_GROUP"),
        "zalo_bot_id": os.getenv("TEST_ZALO_BOT_ID", "kien"),
        "zalo_group_id": os.getenv("TEST_ZALO_GROUP")
    }
    
@pytest.fixture(scope="session")
def request_with_retry():
    """Returns a helper function to make requests with retries for flaky tunnels."""
    def _request(method, url, **kwargs):
        max_retries = 5
        last_exception = None
        for attempt in range(max_retries):
            try:
                # Use timeout from kwargs if provided, otherwise default to 10
                timeout = kwargs.pop("timeout", 10)
                response = requests.request(method, url, timeout=timeout, **kwargs)

                if response.status_code < 500:
                    return response
                print(f">>> Request {method} {url} returned {response.status_code}. Retrying...")
            except (requests.exceptions.RequestException, NameError) as e:
                # NameResolutionError is often wrapped in RequestException
                print(f">>> Attempt {attempt + 1} for {url} failed: {e}")
                last_exception = e
                if attempt < max_retries - 1:
                    time.sleep(2)
                else:
                    raise last_exception
        return None # Should not reach here if max_retries > 0
    return _request
