import pytest
import subprocess
import time
import requests
import os
import signal

@pytest.fixture(scope="session")
def server_process():
    """Starts the FastAPI server for the duration of the test session."""
    cmd = ["./venv/bin/python3", "main.py"]
    env = os.environ.copy()
    env["PORT"] = "8000"
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
    cmd = ["./venv/bin/celery", "-A", "tasks", "worker", "--loglevel=info", "-Q", "celery_receive_message", "--concurrency=1"]
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
        "group_id": os.getenv("TEST_TELEGRAM_GROUP")
    }
