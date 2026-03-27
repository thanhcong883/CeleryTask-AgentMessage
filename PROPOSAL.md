# Đề xuất cải thiện kiến trúc và luồng xử lý Agent Chat Box

Dưới đây là một số đề xuất thực tế để làm cho luồng xử lý hiện tại (Celery + Redis + N8N + Strapi) trở nên nhanh hơn, tin cậy và dễ mở rộng hơn:

## 1. Connection Pooling cho HTTP Requests
**Hiện trạng:** Mỗi task Celery hiện đang tạo một session `requests.get()` hoặc `requests.post()` mới tới Strapi hoặc nền tảng gửi tin nhắn (Zalo/Telegram). Việc thiết lập lại TCP/TLS handshake trên mỗi request làm giảm tốc độ xử lý hàng loạt.
**Đề xuất:**
- Khởi tạo một đối tượng `requests.Session()` toàn cục (global session) trong `api_client.py` và tái sử dụng nó cho mọi request.
- Nếu muốn tối ưu hoá cao hơn, có thể thay thế thư viện `requests` bằng `aiohttp` hoặc `httpx` kết hợp với tính năng Async/Await của Celery (hoặc chuyển hẳn service sang dùng FastAPI backend event-loop).

## 2. Retry Mechanisms và Dead Letter Queue
**Hiện trạng:** Trong `tasks.py`, khi việc gửi tin hoặc đồng bộ API tới Strapi bị lỗi (`check_agent_answer`, `send_message`), hệ thống chỉ ghi ra một dòng log error rồi kết thúc task. Tin nhắn đó có khả năng bị rớt (dropped).
**Đề xuất:**
- Thêm `bind=True` và thuộc tính `default_retry_delay`, `max_retries` vào `@app.task`.
- Khi gọi `provider.send()` hay `update_message()` xảy ra lỗi Timeout/5xx, gọi `self.retry(exc=e)` để thử lại.
- Cấu hình Dead Letter Queue (DLQ) cho RabbitMQ hoặc Celery/Redis để gom các tin nhắn quá giới hạn retry và xử lý lại thủ công sau.

## 3. Bulk Sync Message (Xử lý hàng loạt)
**Hiện trạng:** Khi nhận được tin nhắn (`process_message`), hàm gọi API `sync_message(data)` thực hiện theo từng tin nhắn một.
**Đề xuất:**
- Mặc dù đây là webhook realtime, nếu lượng tin nhắn dồn dập trong 1 giây từ Zalo/Telegram là quá lớn (ví dụ trong Supergroup), có thể đẩy vào một list/buffer Redis.
- Chạy một Celery Beat Task (mỗi 1-2 giây) quét danh sách và gọi API `sync_messages` (batch array) lên Strapi. Điều này giảm số lượng kết nối Database cho Strapi.

## 4. Tối ưu caching và debouncing với Redis
**Hiện trạng:** `admin_active:{conversation_id}` và `bot_processing:{conversation_id}` đang hoạt động ổn để khóa luồng (debouncing).
**Đề xuất:**
- Đối với các query như `get_conversation_info` hay `get_conversation_members` – thông tin này không thay đổi trên từng tin nhắn. Có thể lưu các cache này trên Redis với TTL (Time To Live) ngắn hạn (vd: 5 phút).
- Trước khi gọi `api_get` tới Strapi, hệ thống kiểm tra Redis trước. Sẽ tiết kiệm được ít nhất 2 HTTP requests tới Backend cho mỗi tin nhắn đến.

## 5. Cải thiện cấu trúc Provider
**Hiện trạng:** `PROVIDERS` là một từ điển chứa khởi tạo cứng `TelegramProvider` và `ZaloProvider`.
**Đề xuất:**
- Áp dụng Dependency Injection hoặc Abstract Factory Pattern (Python `abc.ABC`), đăng ký provider một cách linh hoạt (Dynamic Registry).
- Điều này sẽ rất hữu ích trong tương lai khi cần tích hợp WhatsApp, Messenger, Viber mà không phải sửa `tasks.py`.

## Tổng kết
Việc refactor lại code để đảm bảo PEP8 và Type Hints là một bước rất tốt để làm cho dự án "chuyên nghiệp" hơn ở cấp độ bảo trì. Tuy nhiên, ở cấp độ vận hành (Operational), việc áp dụng Session Pool, Celery Retries và Redis Caching sẽ mang lại độ ổn định thực tế và tốc độ phản hồi nhanh hơn rất nhiều.
