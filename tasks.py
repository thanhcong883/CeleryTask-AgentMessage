from celery import Celery
import requests

from provider import PROVIDERS
import config
from update_message import update_message_platform, format_datetime

app = Celery('my_app', broker=config.REDIS_URL)


def update_mess(platform, data, result):
    update_payload = update_message_platform(platform, data, result)
    update_res = requests.put(config.STRAPI_UPDATE_MESSAGE, json=update_payload, headers=config.HEADERS_API_BACKEND)
    print(f"Cập nhật Strapi ID {data.get('message_id')}: {update_res.status_code}")


@app.task(name="task.agent_message", queue="celery_agent_message")
def check_agent_answer(data):

    conversation_id = data.get("conversation")
    message_id = data.get("message_id")
    history_url = config.STRAPI_GET_HISTORY_MESSAGE.format(
        conversation_id=conversation_id,
        message_id=message_id
    )

    history_res = requests.get(history_url, headers=config.HEADERS_API_BACKEND)
    if history_res.status_code != 200:
        print("❌ Không lấy được lịch sử tin nhắn")
        return

    history = history_res.json().get("data", [])
    print(data)
    agent_payload = {
        "question": data.get("content"),
        "history_chat": [
            {
                "role": msg.get("sender_type"),
                "content": msg.get("content"),
                "datetime": msg.get("datetime")
            }
            for msg in history
        ]
    }
    print(f"📨 Payload gửi agent: {agent_payload}")

    try:
        agent_res = requests.post(
            config.N8N_AGENT_WEBHOOK,
            json=agent_payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        print(f"🤖 Đã gửi agent: {agent_res.status_code}")
    except Exception as e:
        print(f"❌ Lỗi gọi agent: {str(e)}")
    
    

     
@app.task(name="tasks.new_msg",queue="celery_receive_message")
def process_message(data):
    res_noti = requests.post(config.STRAPI_SYNC_MESSAGE, json=data, headers=config.HEADERS_API_BACKEND)
    if res_noti.status_code in [200, 201]:
            print(f"✅ Sync to Agent thành công: {res_noti.text}")
    else:
            print(f"⚠️ Sync to Agent thất bại: {res_noti.text}")
    
    conversation_id = res_noti.json()['data'][0]['data']['conversationId']
    message_id = res_noti.json()['data'][0]['data']['messageId']
    
    url = f"{config.STRAPI_GET_CONVERSATION}/{conversation_id}"
    res_inf = requests.get(url, headers=config.HEADERS_API_BACKEND)

    use_agent = res_inf.json().get("data", {}).get("use_agent")
    data_check = {
        "conversation": conversation_id,
        "message_id": message_id,
        "time_to_use_agent": res_inf.json().get("data", {}).get("time_to_use_agent", 0),
        "content": data.get("content"),
        "type": data.get("type"),
        "group_id": data.get("platform_conv_id"),
        "user_id": data.get("platform_user_id"),
        
    } 
    
    print(f"Sử dụng agent: {use_agent}")
    
    if use_agent == True: 
        check_question = requests.post(config.CHECK_QUESTION_API, json={"content": data.get("content")}, headers={"Content-Type": "application/json"})
        print(f"Kết quả kiểm tra câu hỏi: {check_question.text}")
        if check_question.json().get("output") == "true" and data.get("sender_type") == "customer":
           check_agent_answer.apply_async(
                args=[data_check],
                countdown=int(data_check["time_to_use_agent"])
                )
          
            
@app.task(name="tasks.send_message",queue="celery_send_message")
def send_message(data):
    print("Gửi tin nhắn với dữ liệu:", data)
    platform = data.get("platform_id")
    providers = PROVIDERS.get(platform)
    if not providers:
        print(f"Nền tảng {platform} chưa được hỗ trợ.")
        return
    try:
        result = providers.send(data)
        print(f"Kết quả từ {platform}:", result)
        update_mess(platform, data, result)
    except Exception as e:
        print(f"Lỗi hệ thống: {str(e)}")


