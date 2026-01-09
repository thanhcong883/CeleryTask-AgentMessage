from celery import Celery
import requests
from datetime import datetime
from dateutil import parser
from db_config import (
    REDIS_URL, STRAPI_TOKEN, STRAPI_ACCOUNT, 
    STRAPI_CONVERSATION, STRAPI_CONVERSATION_MEMBER,
    STRAPI_MESSAGE, STRAPI_PLATFORM, STRAPI_CUSTOMER,ZALO_ACCESS_TOKEN, TELEGRAM_BOT_TOKEN
)

HEADERS_STRAPI = {"Authorization": STRAPI_TOKEN, "Content-Type": "application/json"}
app = Celery('my_app', broker=REDIS_URL)

def get_strapi_id(endpoint, filters):
    """Chỉ tìm kiếm ID nội bộ dựa trên bộ lọc, không tạo mới"""
    query_parts = [f"filters[{k}][$eq]={v}" for k, v in filters.items()]
    query_url = f"{endpoint}?{'&'.join(query_parts)}"
    try:
        res = requests.get(query_url, headers=HEADERS_STRAPI)
        data = res.json().get('data', [])
        return data[0]['id'] if data else None
    except:
        return None

def upsert_record(endpoint, filters, data):
    """Kiểm tra tồn tại, nếu chưa có thì mới POST tạo mới"""
    existing_id = get_strapi_id(endpoint, filters)
    if existing_id:
        return existing_id
    
    res = requests.post(endpoint, json={"data": data}, headers=HEADERS_STRAPI)
    if res.status_code in [200, 201]:
        return res.json().get('data', {}).get('id')
    return None

@app.task(name="tasks.new_msg")
def process_message(data):

    p_id = str(data.get("platform_id"))
    u_id = str(data.get("platform_user_id") or data.get("sender_id"))
    acc_id = str(data.get("account_id"))
    conv_id = str(data.get("platform_conv_id"))

    # 1. LẤY ID PLATFORM 
    st_p_id = p_id
    # 2. CUSTOMER:
    st_cus_id = upsert_record(
        STRAPI_CUSTOMER, 
        {"platform_user_id": u_id, "platform": st_p_id},
        {"platform": st_p_id, "platform_user_id": u_id, "name": data.get("name")}
    )

    # 3. ACCOUNT: 
    st_acc_id = upsert_record(
        STRAPI_ACCOUNT,
        {"account_id": acc_id},
        {
            "platform": st_p_id, 
            "account_id": acc_id, 
            "name": "Bot Zalo" if p_id == "7" else "Bot Telegram"
        }
    )

    # 4. CONVERSATION:
    st_conv_id = upsert_record(
        STRAPI_CONVERSATION,
        {"platform_conv_id": conv_id, "platform": st_p_id},
        {
            "account": st_acc_id,
            "platform": st_p_id,
            "type": data.get("type"),
            "platform_conv_id": conv_id,
            "title": data.get("title")
        }
    )

    # 5. CONVERSATION MEMBER: 
    upsert_record(
        STRAPI_CONVERSATION_MEMBER,
        {"customer": st_cus_id, "conversation": st_conv_id},
        {
            "role": data.get("role") or "admin",
            "customer": st_cus_id,
            "conversation": st_conv_id,
            "name": data.get("name")
        }
    )

    # 6. MESSAGE:
    message_payload = {
        "conversation": st_conv_id,
        "sender_id": str(data.get("sender_id")),
        "name": data.get("name"),
        "sender_type": data.get("sender_type"),
        "platform_msg_id": str(data.get("platform_msg_id")),
        "content": data.get("content"),
        "datetime": parser.parse(data.get("sender_time")).isoformat()
    }
    requests.post(STRAPI_MESSAGE, json={"data": message_payload}, headers=HEADERS_STRAPI)
    print(f"✅ Đã xử lý xong tin nhắn: {data.get('platform_msg_id')}")
    
# --- TASK GỬI ZALO ---   
@app.task(name="tasks.send_zalo")
def send_zalo_msg(data):
    print("Gửi Zalo:", data)
    headers = {"access_token": ZALO_ACCESS_TOKEN, "Content-Type": "application/json"}
    url = None
    payload = {}
    if data.get("type").strip() == 'private':
        url = "https://openapi.zalo.me/v3.0/oa/message/cs"
        payload = {
            "recipient": {"user_id": data.get("user_id") },
            "message": {"text": data.get("content")}
        }
    elif data.get("type").strip() == "supergroup":  
        url = "https://openapi.zalo.me/v3.0/oa/group/message"
        payload = {
            "recipient": {"group_id": data.get("group_id")},
            "message": {"text": data.get("content")}
        }
    print(url)
    try:
        response = requests.post(url, json=payload, headers=headers)
        result = response.json()
        return {"platform": "Zalo", "status": "success", "response": result}
    except Exception as e:
        return {"platform": "Zalo", "status": "error", "message": str(e)}


# --- TASK GỬI TELEGRAM ---
@app.task(name="tasks.send_tele")
def send_tele_msg(data):
    print("Gửi Telegram:", data)
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": data.get("group_id") if data.get("type").strip() in ["supergroup", "group"] else data.get("user_id"),
        "text": data.get("content"),
    }
    try:
        response = requests.post(url, json=payload)
        result = response.json()
        print(result)
    except Exception as e:
        return {"platform": "Telegram", "status": "error", "message": str(e)}