from celery import Celery
import requests
from datetime import datetime
from dateutil import parser
from db_config import (
    REDIS_URL, STRAPI_TOKEN, STRAPI_ACCOUNT, 
    STRAPI_CONVERSATION, STRAPI_CONVERSATION_MEMBER,
    STRAPI_MESSAGE, STRAPI_PLATFORM, STRAPI_CUSTOMER, STRAPI_UPDATE_MESSAGE,ZALO_ACCESS_TOKEN, TELEGRAM_BOT_TOKEN
)

HEADERS_STRAPI = {"Authorization": STRAPI_TOKEN, "Content-Type": "application/json"}
app = Celery('my_app', broker=REDIS_URL)

def format_datetime(time_val):
    if not time_val:
        return datetime.now().isoformat() 
    try:
        timestamp = float(time_val)
        return datetime.fromtimestamp(timestamp).isoformat()
    except (ValueError, TypeError):
        try:
            return parser.parse(str(time_val)).isoformat()
        except Exception:
            return datetime.now().isoformat()

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
        "customer": st_cus_id,
        "datetime": format_datetime(data.get("sender_time")),
        "status_sender": True
    }
    requests.post(STRAPI_MESSAGE, json={"data": message_payload}, headers=HEADERS_STRAPI)
    print(f"✅ Đã xử lý xong tin nhắn: {data.get('platform_msg_id')}")
    
    
def update_message_status(platform, data, result):    
    mess_id = data.get("message_id")
    if mess_id and result.get("ok"):
        update_url = f"{STRAPI_UPDATE_MESSAGE}"
        print(update_url)
        if platform == "telegram":
            update_payload = {
                "message_id": mess_id,           
                "platform_msg_id": str(result['result']['chat']['id']),    
                "content": result['result']['text'],
                "datetime": format_datetime(result['result']['date']),
                "status": "sent"
            }
        elif platform == "zalo":
            update_payload = {
                "message_id": mess_id,           
                "platform_msg_id": str(result['message_id']), 
                "content": data.get("content"),
                "datetime": format_datetime(data.get("sent_time")),
                "status": "sent"
            }
        HEADERS_UPDATE_MESS = {
            "Content-Type": "application/json",
            "x-webhook-secret": "k7P2mR9vX4"
        }
        update_res = requests.put(update_url, json=update_payload, headers=HEADERS_UPDATE_MESS)
        print(f"Cập nhật Strapi ID {mess_id}: {update_res.status_code}")
        
            
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
    response = requests.post(url, json=payload, headers=headers)
    result = response.json()
    print("Kết quả gửi Zalo:", result)
    update_message_status("zalo", data, result)



# --- TASK GỬI TELEGRAM ---
@app.task(name="tasks.send_tele")
def send_tele_msg(data):
    
    print("Gửi Telegram:", data)
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": data.get("group_id") if data.get("type").strip() in ["supergroup", "group"] else data.get("user_id"),
        "text": data.get("content"),
    }
    response = requests.post(url, json=payload)
    result = response.json()
    print("Kết quả gửi Telegram:", result)
    update_message_status("telegram", data, result)
