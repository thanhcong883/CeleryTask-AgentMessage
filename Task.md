# Tasks Reference

This document lists the Celery tasks and their respective inputs, outputs, and purposes within the system.

---

## 1. `process_message`
- **Name**: `tasks.new_msg`
- **Queue**: `celery_receive_message`
- **Purpose**: Acts as the main entry point for processing incoming messages from various platforms (Telegram, Zalo). It syncs the message with the Strapi backend, checks conversation settings (like agent enablement), determines user roles, and schedules further agent processing if necessary.
- **Inputs**:
  - `data`:
    ```json
    {
      "sender_type": "customer",
      "sender_id": "6657524365",
      "platform_msg_id": "512",
      "content": "Ok a",
      "sender_time": "1774500173",
      "platform_id": "8",
      "account_id": "8796872230",
      "type": "group",
      "name": "Trịnh Công Đạt",
      "title": "Server Thế Anh Đẹp Trai\n",
      "platform_user_id": "6657524365",
      "platform_conv_id": "-4076154503",
      "role": null,
      "token": "",
      "platform_name": "Telegram"
    }
    ```
- **Outputs**: None.

## 2. `check_agent_answer`
- **Name**: `tasks.check_agent_answer`
- **Queue**: `celery_receive_message`
- **Purpose**: Evaluates whether an automated agent can respond to a user's question based on message history and current bot status. If the agent cannot answer, it notifies admins and the customer.
- **Inputs**:
  - `data`:
    ```json
    {
      "conversation": "conversation_id",
      "message_id": "message_id",
      "time_to_use_agent": "time_to_use_agent",
      "content": "data.get('content')",
      "type": "conversation_info.get('type')",
      "platform_conv_id": "data.get('platform_conv_id')",
      "group_id": "data.get('platform_conv_id')",
      "user_id": "data.get('platform_user_id')",
      "platform_name": "data.get('platform_name')",
      "bot_message": "conversation_info.get('bot_message', '')",
      "token": "data.get('token')",
      "title": "conversation_info.get('title')",
      "bot_sent_to": "conversation_info.get('bot_sent_to')"
    }
    ```
- **Outputs**: None.

## 3. `send_message`
- **Name**: `tasks.send_message`
- **Queue**: `celery_send_message`
- **Purpose**: Responsible for sending messages to a specific platform (Telegram, Zalo) and updating the message status in the Strapi backend once sent.
- **Inputs**:
  - `data`:
    ```json
    {
      "type": "group",
      "group_id": "-5252794402",
      "user_id": "-5252794402",
      "content": "lko",
      "platform_name": "Telegram",
      "message_id": "1373",
      "token": ""
    }
    ```
  - `data_send` (Optional): Metadata for logging bot-sent messages.
- **Outputs**: None.
