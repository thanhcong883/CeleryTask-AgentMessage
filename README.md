# Celery Task

Sử dụng celery để làm interface thực hiện các task gửi/nhận tin đa nền tảng. 

## Luồng tổng quát
- Gửi tin nhắn:
```
front-end -> API -> n8n -> redis -> celery(task) -> db
```
- Nhận tin nhắn:
```
Platform_message -> n8n -> redis -> celery(task) -> db 
```
### Luồng gửi tin nhắn

- Từ giao diện khi người dùng soạn tin nhắn và gửi, backend sẽ lưu tạm thời tin nhắn đã gửi vào db, trường **"message_status"** sẽ được gán là **wait**, và để trống trường **"platform_msg_id"**. 
- Sau đó backend sẽ gửi các trường **"User_id"** hoặc **"group_id"**, **platform_id**, và **"message_id"** mà backend đã lưu tới N8N. N8N sẽ gửi dữ liệu vào Redis.
-  Celery Task sẽ thực hiện nhiệm vụ lấy data mà backend đã gửi. Thực hiện gọi API để gửi tin nhắn đến các nền tảng. Từ kết quả API gửi tin nhắn, sẽ có được trường **"platform_msg_id"**. Lấy **datetime** đã được gửi, sau đó chỉnh sửa các trường **datetime**, **"platform_msg_id"**,**"message_status"** trong db dựa trên **"message_id"** đã nhận được 

### Luồng nhận tin nhắn

- Sau khi có tin nhắn đến, N8N sẽ thực hiện gọi API trích xuất các trường cần thiết để lưu vào db. Sau khi có được data gồm các trường dưới đây, nó sẽ gửi data vào redis.
```
{
"sender_type": "customer",
"sender_id": "1727763159199846722",
"platform_msg_id": "bb4eb0fbcf66e63ebf71",
"content": "Trong lúc nó tích hợp thì triển khai song song",
"sender_time": "2026-01-13T03:29:39.842Z",
"platform_id": "7",
"account_id": "95759257550957582",
"type": "supergroup",
"name": "Nguyễn Hữu Kiên",
"title": "Test",
"platform_user_id": "1727763159199846722",
"platform_conv_id": "f4bdb2afcfce26907fdf",
"role": "customer"
}
```
- Celery sẽ đọc data ở redis rồi bắt đầu lưu vào DB. Đầu tiên lưu bảng **Customer**, nếu đã tồn tại **"platform_user_id"** trùng với **"platform_user_id"** đã nhận thì bỏ qua không lưu. Tương tự đối với các bảng tiếp theo là 
```
Account -> Conversation -> Conversation Member -> Message
