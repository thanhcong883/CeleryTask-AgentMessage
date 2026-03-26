#!/bin/bash

# Ensure services are cleaned up
./kill_services.sh

# Run only non-manual tests
echo ">>> Running non-manual tests..."
if [ -f .env.test ] && grep -q "TEST_TELEGRAM_TOKEN=" .env.test && grep -q "TEST_TELEGRAM_GROUP=" .env.test; then
    ./venv/bin/pytest -k "not manual"
else
    echo "Skipping tests: .env.test is missing or incomplete."
fi
