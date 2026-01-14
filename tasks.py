from celery import Celery
import requests

from provider import PROVIDERS
import config
from update_message import update_message_platform, format_datetime
HEADERS_STRAPI = {"Authorization": config.STRAPI_TOKEN, "Content-Type": "application/json"}
app = Celery('my_app', broker=config.REDIS_URL)


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

def update_mess(platform, data, result):
    update_payload = update_message_platform(platform, data, result)
    update_res = requests.put(config.STRAPI_UPDATE_MESSAGE, json=update_payload, headers=config.HEADERS_UPDATE_MESS)
    print(f"Cập nhật Strapi ID {data.get('message_id')}: {update_res.status_code}")
        
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
        config.STRAPI_CUSTOMER, 
        {"platform_user_id": u_id, "platform": st_p_id},
        {"platform": st_p_id, "platform_user_id": u_id, "name": data.get("name")}
    )

    # 3. ACCOUNT: 
    st_acc_id = upsert_record(
        config.STRAPI_ACCOUNT,
        {"account_id": acc_id},
        {
            "platform": st_p_id, 
            "account_id": acc_id, 
            "name": "Bot Zalo" if p_id == "7" else "Bot Telegram"
        }
    )

    # 4. CONVERSATION:
    st_conv_id = upsert_record(
        config.STRAPI_CONVERSATION,
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
        config.STRAPI_CONVERSATION_MEMBER,
        {"customer": st_cus_id, "conversation": st_conv_id},
        {
            "role": data.get("role") ,
            "customer": st_cus_id,
            "conversation": st_conv_id,
        }
    )

    # 6. MESSAGE:
    message_payload = {
        "conversation": st_conv_id,
        "sender_id": str(data.get("sender_id")),
        "sender_type": data.get("sender_type"),
        "platform_msg_id": str(data.get("platform_msg_id")),
        "content": data.get("content"),
        "datetime": format_datetime(data.get("sender_time")),
        "message_status": "sent"
    }
    res=requests.post(config.STRAPI_MESSAGE, json={"data": message_payload}, headers=HEADERS_STRAPI)
    print(f"✅ Đã xử lý xong tin nhắn: {data.get('platform_msg_id')}")
            
@app.task(name="tasks.send_message")
def send_message(data):
    platform = data.get("platform_id")
    provider = PROVIDERS.get(platform)
    if not provider:
        print(f"Nền tảng {platform} chưa được hỗ trợ.")
        return
    try:
        result = provider.send(data)
        print(f"Kết quả từ {platform}:", result)
        update_mess(platform, data, result)
    except Exception as e:
        print(f"Lỗi hệ thống: {str(e)}")
