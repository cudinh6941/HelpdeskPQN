# Tích hợp n8n với Transactional Outbox của IT Helpdesk

Thư mục này cung cấp workflow mẫu để nhận sự kiện từ worker `outbox_dispatcher` của Helpdesk, xác thực chữ ký HMAC-SHA256 (`X-Helpdesk-Signature`) và điều phối thông báo qua Telegram / Email.

## 1. Import workflow vào n8n
1. Mở giao diện n8n -> chọn **Workflows** -> **Import from File**.
2. Chọn file [helpdesk-notifications-workflow.json](./helpdesk-notifications-workflow.json).
3. Cấu hình các biến môi trường cho n8n:
   - `N8N_WEBHOOK_SECRET`: trùng với biến `N8N_WEBHOOK_SECRET` trong `.env` của Helpdesk (mặc định `helpdesk-n8n-secret`).
   - `TELEGRAM_BOT_TOKEN` & `TELEGRAM_IT_GROUP_CHAT_ID`: token Bot Telegram và Chat ID nhóm IT nhận cảnh báo ticket mới / SLA.
   - Cấu hình SMTP Credential trong node **Requester Email Update**.
4. Bấm **Active** để bật workflow và lấy Production Webhook URL (ví dụ `http://host.docker.internal:5678/webhook/it-helpdesk`).

## 2. Bật gửi webhook thật trên Helpdesk
Trong file `.env` ở thư mục gốc của project:
```env
N8N_WEBHOOK_URL=http://host.docker.internal:5678/webhook/it-helpdesk
N8N_WEBHOOK_SECRET=helpdesk-n8n-secret
N8N_DRY_RUN=false
```
Sau đó khởi động lại backend & worker:
```powershell
docker compose up -d backend worker
```

## 3. Kiểm tra trạng thái gửi
- Vào **Settings -> Outbox Log** (`/workspace/admin`) để xem trạng thái từng event (`PENDING`, `SENT`, `FAILED`).
- Nếu n8n tạm thời tắt, worker tự retry theo backoff (`MAX_RETRIES = 5`), và IT Lead/Admin có thể bấm nút **Retry** ngay trên UI.

