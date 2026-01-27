from celery import Celery
import requests

from provider import PROVIDERS
import config
from update_message import update_message_platform

app = Celery('my_app', broker=config.REDIS_URL)


def handle_send_message(data, callback=None):
    platform = data.get("platform_id")
    if not platform:
        print("ERROR: Platform ID missing.")
        return

    providers = PROVIDERS.get(platform)
    if not providers:
        print(f"ERROR: Platform {platform} not supported.")
        return

    try:
        result = providers.send(data)
        if callback:
            callback(platform, data, result)
    except Exception as e:
        print(f"ERROR: Failed to send message for {platform}: {e}")


@app.task(name="task.agent_message", queue="celery_agent_message")
def check_agent_answer(data):
    conversation_id = data.get("conversation")
    message_id = data.get("message_id")
    history_url = config.STRAPI_GET_HISTORY_MESSAGE.format(
        conversation_id=conversation_id,
        message_id=message_id
    )

    try:
        history_res = requests.get(history_url, headers=config.HEADERS_API_BACKEND)
        history_res.raise_for_status()
        history = history_res.json().get("data", [])
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Failed to get message history: {e}")
        return

    agent_payload = {
        "question": data.get("content"),
        "history_chat": [{"role": msg.get("sender_type"), "content": msg.get("content"), "datetime": msg.get("datetime")} for msg in history]
    }

    try:
        agent_res = requests.post(
            config.N8N_AGENT_WEBHOOK,
            json=agent_payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        agent_res.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Agent call failed: {e}")
        return

    if agent_res.json().get("output") == "false":
        send_admin_payload = {
            "type": "group",
            "group_id": data.get("group_id"),
            "content": data.get("bot_message"),
            "platform_id": data.get("platform_id"),
            "platform_conv_id": data.get("platform_conv_id")
        }
        send_message.apply_async(
            args=[send_admin_payload, data],
            queue="celery_send_message"
        )


@app.task(name="tasks.new_msg", queue="celery_receive_message")
def process_message(data):
    try:
        res_noti = requests.post(config.STRAPI_SYNC_MESSAGE, json=data, headers=config.HEADERS_API_BACKEND)
        res_noti.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Sync to Agent failed: {e}")
        return

    try:
        noti_data = res_noti.json().get('data', [])
        conversation_id = noti_data[0].get('data', {}).get('conversationId') if noti_data else None
        message_id = noti_data[0].get('data', {}).get('messageId') if noti_data else None

        if not (conversation_id and message_id):
            print("ERROR: Missing conversationId or messageId in sync notification response.")
            return

    except (ValueError, IndexError):
        print("ERROR: Failed to parse JSON or access data from sync notification response.")
        return

    res_member_url = config.STRAPI_GET_CONVERSATION_MEMBER.format(conversation_id=conversation_id)
    try:
        res_member = requests.get(res_member_url, headers=config.HEADERS_API_BACKEND)
        res_member.raise_for_status()
        member = res_member.json().get("data", [])
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Failed to retrieve members: {e}")
        return
    except ValueError:
        print("ERROR: Failed to parse JSON from member retrieval response.")
        return

    role_app = next(
        (m.get("role_app") for m in member if m.get("customer", {}).get("platform_user_id") == data.get("platform_user_id")),
        None
    )

    if role_app == "admin":
        return
    else:
        url = f"{config.STRAPI_GET_CONVERSATION}/{conversation_id}"
        try:
            res_inf = requests.get(url, headers=config.HEADERS_API_BACKEND)
            res_inf.raise_for_status()
            conversation_info = res_inf.json().get("data", {})
            use_agent = conversation_info.get("use_agent")
            time_to_use_agent = conversation_info.get("time_to_use_agent", 0)
            bot_message = conversation_info.get("bot_message", "")
        except requests.exceptions.RequestException as e:
            print(f"ERROR: Failed to retrieve conversation info: {e}")
            return
        except ValueError:
            print("ERROR: Failed to parse JSON from conversation info response.")
            return

        data_check = {
            "conversation": conversation_id,
            "message_id": message_id,
            "time_to_use_agent": time_to_use_agent,
            "content": data.get("content"),
            "type": data.get("type"),
            "platform_conv_id": data.get("platform_conv_id"),
            "group_id": data.get("platform_conv_id"),
            "user_id": data.get("platform_user_id"),
            "platform_id": data.get("platform_id"),
            "bot_message": bot_message
        }

        if use_agent and data.get("sender_type") == "customer":
            try:
                check_question_res = requests.post(config.CHECK_QUESTION_API, json={"content": data.get("content")}, headers={"Content-Type": "application/json"})
                check_question_res.raise_for_status()
                if check_question_res.json().get("output") == "true":
                    check_agent_answer.apply_async(
                        args=[data_check],
                        countdown=int(time_to_use_agent)
                    )
            except requests.exceptions.RequestException as e:
                print(f"ERROR: Failed to check question or call agent: {e}")
            except ValueError:
                print("ERROR: Failed to parse JSON from question check response.")


@app.task(name="tasks.send_message", queue="celery_send_message")
def send_message(data, data_check=None): # data_check added for bot message context
    def on_success_callback(platform, message_data, send_result):
        # Logic for updating message platform
        update_payload = update_message_platform(platform, message_data, send_result)
        try:
            update_res = requests.put(config.STRAPI_UPDATE_MESSAGE, json=update_payload, headers=config.HEADERS_API_BACKEND)
            update_res.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"ERROR: Failed to update Strapi ID {message_data.get('message_id')}: {e}")

        # Logic for saving bot-sent message, if data_check is provided
        if data_check:
            data_bot_sent = {
                "sender_type": "bot",
                "sender_id": "",
                "platform_msg_id": update_payload.get("platform_msg_id"),
                "content": data_check.get("bot_message"),
                "datetime": update_payload.get("datetime"),
                "platform_conv_id": message_data.get("platform_conv_id"),
                "message_status": "sent"
            }
            try:
                res_bot_sent = requests.post(config.STRAPI_SAVE_MESSAGE_BOT_SENT, json=data_bot_sent, headers=config.HEADERS_API_BACKEND)
                res_bot_sent.raise_for_status()
            except requests.exceptions.RequestException as e:
                print(f"ERROR: Failed to save bot message: {e}")
    handle_send_message(data, callback=on_success_callback)