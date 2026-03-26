#!/bin/bash

# Kill FastAPI server
echo "Killing FastAPI server..."
pkill -f "python3 main.py"

# Kill Celery workers
echo "Killing Celery workers..."
pkill -f celery

# Kill Pytest
echo "Killing Pytest..."
pkill -f pytest

# Check ports
echo "Checking ports 8000 and 8001..."
# Use lsof if fuser is missing
if command -v lsof >/dev/null 2>&1; then
    lsof -ti:8000 | xargs kill -9 2>/dev/null
    lsof -ti:8001 | xargs kill -9 2>/dev/null
else
    echo "Warning: lsof not found, could not check ports directly. Use 'ps aux | grep python' to verify."
fi

echo "All services stopped."
rm server_test.log
rm worker_test.log