#!/bin/bash
export $(grep -v '^#' .env.test | xargs)

echo "Creating bot..."
curl -X POST http://localhost:8000/api/bots \
     -H "Content-Type: application/json" \
     -d "{
       \"botId\": \"test_tg_bot\",
       \"options\": {
         \"platform\": \"telegram\",
         \"token\": \"$TEST_TELEGRAM_TOKEN\"
       }
     }"
echo -e "\n"

echo "Checking status..."
curl http://localhost:8000/api/bots/test_tg_bot/status
echo -e "\n"

echo "Sending message..."
curl -X POST http://localhost:8000/api/bots/test_tg_bot/send \
     -H "Content-Type: application/json" \
     -d "{
       \"content\": \"Hello world from script!\",
       \"group_id\": \"$TEST_TELEGRAM_GROUP\",
       \"type\": \"group\"
     }"
echo -e "\n"

echo "Deleting bot..."
curl -X DELETE http://localhost:8000/api/bots/test_tg_bot
echo -e "\n"
