import pytest
import subprocess
import time
import requests
import os
import signal
import re

@pytest.fixture(scope="session")
def tunnel_url(server_process):
    """Starts a localtunnel and returns the public URL."""
    # pylt MUST run after server started to verify local port 8000
    cmd = ["pylt", "port", "8000"]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, preexec_fn=os.setsid)
    
    url = None
    max_retries = 20
    for _ in range(max_retries):
        line = process.stdout.readline()
        if "Your url is:" in line:
            url = line.split("is:")[1].strip()
            break
        time.sleep(1)
    
    if not url:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        raise RuntimeError("Failed to get localtunnel URL")
    
    print(f"\n>>> TUNNEL OPENED: {url}")
    
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
def server_process():
    """Starts the FastAPI server for the duration of the test session."""
    cmd = ["python3", "main.py"]
    env = os.environ.copy()
    env["PORT"] = "8000"
    # Initial BASE_URL is localhost, will be updated by tunnel_url fixture
    env["BASE_URL"] = "http://localhost:8000"
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
def worker_process():
    """Starts the Celery worker for the duration of the test session."""
    cmd = ["celery", "-A", "tasks", "worker", "--loglevel=info", "-Q", "celery_receive_message,celery_send_message,celery_agent_message", "--concurrency=1"]
    log_file = open("worker_test.log", "w")
    process = subprocess.Popen(cmd, stdout=log_file, stderr=log_file, preexec_fn=os.setsid)
    
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
    load_dotenv(".env.test")
    return {
        "token": os.getenv("TEST_TELEGRAM_TOKEN"),
        "token_2": os.getenv("TEST_TELEGRAM_TOKEN_2"),
        "group_id": os.getenv("TEST_TELEGRAM_GROUP"),
        "zalo_bot_id": os.getenv("TEST_ZALO_BOT_ID", "kien"),
        "zalo_group_id": os.getenv("TEST_ZALO_GROUP")
    }
