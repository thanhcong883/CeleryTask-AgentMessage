
from datetime import datetime
from dateutil import parser

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
        
def update_message_platform(platform, data, result):    
    mess_id = data.get("message_id")
    update_payload = {}
    print(result)
    if mess_id:
        if platform == "8":
            update_payload = {
                "message_id": mess_id,           
                "platform_msg_id": str(result['result']['message_id']),    
                "content": result['result']['text'],
                "datetime": format_datetime(result['result']['date']),
                "message_status": "sent"
            }
            return update_payload
        elif platform == "7":
            update_payload = {
                "message_id": mess_id,           
                "platform_msg_id": str(result['data']['message_id']), 
                "content": data.get("content"),
                "datetime": format_datetime(data.get("sent_time")),
                "message_status": "sent"
            }

            return update_payload
