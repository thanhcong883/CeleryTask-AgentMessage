import requests


class TelegramProvider:
    def send(self, data):
        url = data.get("url", "").format(token=data.get("token", ""))
        payload = {
            "chat_id": data.get("group_id")
            if data.get("type") in ["group", "supergroup"]
            else data.get("user_id"),
            "text": data.get("content"),
        }
        return requests.post(url, json=payload, timeout=10).json()


class ZaloProvider:
    def send(self, data):
        print("Gửi tin nhắn Zalo với dữ liệu:", data)
        is_private = data.get("type").strip() == "private"
        url = data.get("private_url") if is_private else data.get("group_url")
        headers = {"access_token": data.get("token")}
        payload = {
            "recipient": {
                "user_id" if is_private else "group_id": data.get(
                    "user_id" if is_private else "group_id"
                )
            },
            "message": {"text": data.get("content")},
        }
        return requests.post(url, json=payload, headers=headers, timeout=10).json()


PROVIDERS = {"Telegram": TelegramProvider(), "Zalo": ZaloProvider()}
