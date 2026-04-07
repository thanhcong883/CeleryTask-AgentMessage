#!/bin/bash
# .devcontainer/setup-dev.sh

set -e

# 1. Install Redis and dependencies
echo ">>> Installing Redis and system tools..."
sudo apt-get update && sudo apt-get install -y redis-server curl python3-venv

# 2. Start Redis server in the background
echo ">>> Starting Redis server..."
redis-server --requirepass redispass --daemonize yes

# 3. Handle Python virtual environment
echo ">>> Creating/Updating Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

# 4. Install requirements into venv
echo ">>> Installing requirements into venv..."
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt pytest pytest-mock

# 5. Install cloudflared (for tunnel tests)
echo ">>> Installing cloudflared..."
if ! command -v cloudflared &> /dev/null; then
    curl -L --output /tmp/cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
    dpkg -i /tmp/cloudflared.deb
    rm /tmp/cloudflared.deb
fi

# 6. Check if Redis is running
if redis-cli -a redispass ping | grep -q "PONG"; then
    echo ">>> Redis is UP!"
else
    echo ">>> Failed to start Redis."
fi

echo ">>> Dev environment setup complete!"
