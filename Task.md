# Tasks Reference

This document lists the Celery tasks and their respective inputs, outputs, and purposes within the system.

---

## 1. `process_message`
- **Name**: `tasks.new_msg`
- **Queue**: `celery_receive_message`
- **Purpose**: Acts as the main entry point for processing incoming messages from various platforms (Telegram, Zalo). It syncs the message with the Strapi backend, checks conversation settings (like agent enablement), determines user roles, and schedules further agent processing if necessary.
- **Inputs**:
  - `data`: A dictionary containing message details from the platform (e.g., `platform_name`, `content`, `platform_user_id`, etc.).
- **Outputs**: None.

## 2. `check_agent_answer`
- **Name**: `tasks.check_agent_answer`
- **Queue**: `celery_receive_message`
- **Purpose**: Evaluates whether an automated agent can respond to a user's question based on message history and current bot status. If the agent cannot answer, it notifies admins and the customer.
- **Inputs**:
  - `data`: A dictionary including `conversation`, `message_id`, `content`, `platform_name`, and other relevant conversation metadata.
- **Outputs**: None.

## 3. `send_message`
- **Name**: `tasks.send_message`
- **Queue**: `celery_send_message`
- **Purpose**: Responsible for sending messages to a specific platform (Telegram, Zalo) and updating the message status in the Strapi backend once sent.
- **Inputs**:
  - `data`: The message data to be sent (including platform-specific details and credentials).
  - `data_send` (Optional): Metadata for logging bot-sent messages.
- **Outputs**: None.
