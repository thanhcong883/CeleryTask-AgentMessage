#!/bin/bash

# Ensure services are cleaned up
./kill_services.sh

# Run only manual tests
echo ">>> Running manual tests..."
if [ -f .env.test ] && grep -q "TEST_TELEGRAM_TOKEN=" .env.test && grep -q "TEST_TELEGRAM_GROUP=" .env.test; then
    ./venv/bin/pytest -k "manual"
else
    echo "Skipping tests: .env.test is missing or incomplete."
fi
