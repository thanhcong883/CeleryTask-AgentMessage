---
description: how to test the bot management API
---

# Testing the Bot Management API

This workflow describes how to start the server, the Celery worker, and test the API endpoints for each platform.

### Prerequisites

- Ensure the virtual environment is created and dependencies are installed.
- Ensure Redis is running and the `.env` file is configured.

### 1. Start the Server

Using .env



```bash
./venv/bin/python3 main.py
```

The server will start at `http://0.0.0.0:8000`.

### 2. Start the Celery Worker

Open another terminal and run:

```bash
./venv/bin/celery -A tasks worker --loglevel=info -Q celery_receive_message --concurrency=2
```

### 3. Test API Endpoints

First, export the test information from `.env.test`:

```bash
export $(grep -v '^#' .env.test | xargs)
```

You can then use the following `curl` commands to test the API.

#### Create a Telegram Bot

// turbo
```bash
curl -X POST http://localhost:8000/api/bots \
     -H "Content-Type: application/json" \
     -d "{
       \"botId\": \"test_tg_bot\",
       \"options\": {
         \"platform\": \"telegram\",
         \"token\": \"$TEST_TELEGRAM_TOKEN\"
       }
     }"
```

#### Get Bot Status

// turbo
```bash
curl http://localhost:8000/api/bots/test_tg_bot/status
```

#### Send a Message via the Bot

// turbo
```bash
curl -X POST http://localhost:8000/api/bots/test_tg_bot/send \
     -H "Content-Type: application/json" \
     -d "{
       \"content\": \"Hello world from test!\",
       \"user_id\": \"$TEST_TELEGRAM_GROUP\",
       \"type\": \"group\"
     }"
```

#### Create a Zalo Bot

// turbo
```bash
curl -X POST http://localhost:8000/api/bots \
     -H "Content-Type: application/json" \
     -d '{
       "botId": "test_zalo_bot",
       "options": {
         "platform": "zalo"
       }
     }'
```

#### Delete a Bot

// turbo
```bash
curl -X DELETE http://localhost:8000/api/bots/test_tg_bot
```

### 4. Human-in-the-loop Testing (Real-world Verification)

This section describes how to verify that the bot is correctly receiving and processing real messages.

1. **Start the Server and Worker** as described in steps 1 and 2.
2. **Create a Bot** with a valid token.
3. **Send a Message Manually**: Open your Telegram/Zalo app and send a message to the bot.
4. **Check Worker Logs**: Observe the Celery worker terminal. You should see logs indicating:
   - `Received Telegram message from ...`
   - `API Request (POST): .../sync-message`
5. **Verify Syncing**: If the `.env` is correctly configured with Strapi/N8N URLs, the message should be successfully synced. If you see connection errors (e.g., to `localhost:1337`), it means the backend service is not running, but the bot **correctly received the message**.
6. **Confirm with User**: Ask the user to send some message on test group
7. Confirm message received

#### Manual Verification Example

> [!TIP]
> Use the following command to follow the logs in real-time while you send a message:
> `tail -f server.log` (if logging to a file) or simply watch the stdout of the worker process.