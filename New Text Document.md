# IT HELPDESK SYSTEM — ARCHITECTURE & IMPLEMENTATION BLUEPRINT

## 1. TỔNG QUAN & MỤC TIÊU

- **Mục tiêu:** Cổng tiếp nhận và xử lý sự cố IT nội bộ (Helpdesk) tối giản cho người dùng cuối, chặt chẽ về nghiệp vụ/SLA cho đội ngũ IT, tách biệt khỏi hệ thống quản lý tài sản sẵn có (chỉ tham chiếu qua `asset_code`).
- **Nguyên tắc thiết kế:**
  - UX siêu gọn cho nhân viên (10 giây tạo xong ticket, hỗ trợ dán ảnh `Ctrl+V`).
  - Kiến trúc tách lớp, sẵn sàng mở rộng đa phòng ban/nhóm kỹ thuật và phục vụ phân tích dữ liệu (SQL/Data Warehouse).
  - Tin cậy tuyệt đối trong thông báo (Transactional Outbox Pattern -> n8n -> Email + Telegram/Zalo Bot).

---

## 2. TECH STACK & HẠ TẦNG

- **Frontend:** Next.js (App Router) + TypeScript + Tailwind CSS + shadcn/ui + Lucide Icons.
- **Backend API:** Python 3.12+ + FastAPI + Pydantic v2 + SQLAlchemy 2.0 (Async) + Alembic.
- **Database:** PostgreSQL 16 (sử dụng `UUIDv7` cho khóa chính giao dịch, `JSONB` cho dữ liệu mở rộng).
- **Object Storage:** MinIO (Self-hosted S3) lưu trữ tệp đính kèm qua Presigned URL (kèm fallback lưu trữ cục bộ / proxy upload an toàn).
- **Authentication & RBAC:** Corporate **LDAP / Active Directory** (`ldap3`) + Signed JWT Access Token — 4 vai trò: `END_USER`, `IT_AGENT`, `IT_LEAD`, `SYS_ADMIN` (hỗ trợ đồng bộ tự động user từ AD vào bảng `users` và local fallback cho môi trường dev/test).
- **Event & Notification:** Transactional Outbox Worker (`SELECT ... FOR UPDATE SKIP LOCKED`) -> Webhook **n8n** -> SMTP Email + Telegram/Zalo Bot.
- **Deployment:** Docker Compose + Caddy (Reverse Proxy & Internal HTTPS).

---

## 3. CẤU TRÚC THƯ MỤC MONOREPO

```text
HelpdeskPQN/
├── docker-compose.yml          # Orchestration: caddy, frontend, backend, worker, db, minio
├── Caddyfile                   # Reverse proxy & TLS internal
├── .env.example                # Biến môi trường chuẩn
├── README.md                   # Tài liệu triển khai & vận hành
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/                # Database migrations
│   ├── tests/                  # Pytest suite (Auth, State Machine, SLA, Outbox)
│   └── app/
│       ├── core/               # Config, Security (LDAP + JWT), DB session, UUIDv7, MinIO client
│       ├── models/             # SQLAlchemy 2.0 models (11 bảng)
│       ├── schemas/            # Pydantic v2 request/response schemas
│       ├── api/v1/             # Endpoints: auth, tickets, comments, attachments, admin, analytics
│       ├── services/           # Business logic: SLA engine, Ticket state machine, Outbox writer
│       └── workers/            # Background workers: Outbox dispatcher (gọi n8n), SLA scanner
└── frontend/
    ├── Dockerfile
    ├── package.json
    └── src/
        ├── app/                # Next.js App Router (Login, Portal user & Workspace IT)
        ├── components/         # UI components (PasteImageUploader, TicketTimeline, AppShell)
        └── lib/                # API client, Auth context, Types
```

---

## 4. THIẾT KẾ DATABASE (11 BẢNG POSTGRESQL + UUIDv7)

| STT | Bảng | Mô tả & Trường chính |
| :--- | :--- | :--- |
| 1 | `departments` | Phòng ban nội bộ (`id`, `code`, `name`, `is_active`). |
| 2 | `users` | Nhân sự đồng bộ từ LDAP/AD (`id`, `username`, `ldap_dn`, `email`, `full_name`, `role`, `department_id`, `telegram_chat_id`, `zalo_user_id`). |
| 3 | `support_groups` | Nhóm kỹ thuật IT (`id`, `code`, `name`, `description`, `is_active`). |
| 4 | `support_group_members` | Thành viên thuộc nhóm IT (`group_id`, `user_id`, `is_lead`). |
| 5 | `sla_policies` | Chính sách SLA theo mức ưu tiên `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` (`first_response_minutes`, `resolution_minutes`, `warning_threshold_pct`, `business_hours_only`). |
| 6 | `business_calendars` | Giờ hành chính & danh sách ngày nghỉ lễ `holidays` (`JSONB`). |
| 7 | `categories` | Danh mục sự cố (`parent_id`, `name`, `slug`, `default_group_id`, `default_priority`, `form_schema` `JSONB`). |
| 8 | `tickets` | Bảng trung tâm (`ticket_code`, `title`, `description`, `status`, `priority`, `requester_id`, `assignee_id`, `support_group_id`, `category_id`, `sla_policy_id`, `asset_code`, `custom_data` `JSONB`, các mốc SLA & `sla_paused_at`, `total_paused_seconds`, `rating`, `feedback`). |
| 9 | `ticket_comments` | Trao đổi công khai & Ghi chú nội bộ (`is_internal=true` ẩn với `END_USER`). |
| 10 | `ticket_attachments` | Metadata tệp/ảnh `Ctrl+V` trên MinIO (`bucket_name`, `object_key`, `file_name`, `content_type`, `size_bytes`, `is_uploaded`). |
| 11 | `outbox_events` | Transactional Outbox & Audit Timeline (`aggregate_id`, `actor_id`, `event_type`, `payload` `JSONB`, `status`, `retry_count`, `next_retry_at`). |

---

## 5. TICKET STATE MACHINE & SLA ENGINE

- **Các trạng thái hợp lệ:**
  - `NEW` -> `ASSIGNED` | `IN_PROGRESS` | `CANCELLED`
  - `ASSIGNED` -> `IN_PROGRESS` | `WAITING_FOR_USER` | `CANCELLED`
  - `IN_PROGRESS` -> `WAITING_FOR_USER` | `RESOLVED` | `ASSIGNED`
  - `WAITING_FOR_USER` -> `IN_PROGRESS` | `RESOLVED` | `CLOSED`
  - `RESOLVED` -> `CLOSED` | `REOPENED`
  - `REOPENED` -> `IN_PROGRESS` | `WAITING_FOR_USER` | `RESOLVED`
- **Tạm dừng & Cộng bù SLA:**
  - Khi chuyển sang `WAITING_FOR_USER`: lưu `sla_paused_at = now`.
  - Khi người dùng phản hồi hoặc IT chuyển lại `IN_PROGRESS`: cộng dồn `paused_delta` vào `total_paused_seconds` và tịnh tiến `resolution_due_at += paused_delta`.
- **Phản hồi đầu tiên (`first_responded_at`):** Tự động ghi nhận khi IT Agent nhận việc (`claim`), phân công hoặc gửi phản hồi công khai đầu tiên.

---

## 6. TRANSACTIONAL OUTBOX & CONTRACT WEBHOOK N8N

Mọi thay đổi nghiệp vụ trên Ticket ghi nhận `outbox_events` **trong cùng DB transaction**. Worker `outbox_dispatcher` đọc bằng `SELECT ... FOR UPDATE SKIP LOCKED` và gửi `POST` tới `N8N_WEBHOOK_URL` kèm header chữ ký `X-Helpdesk-Signature` (HMAC-SHA256):

```json
{
  "event_id": "019...",
  "event_type": "TICKET_CREATED | TICKET_ASSIGNED | STATUS_CHANGED | COMMENT_ADDED | SLA_WARNING | SLA_BREACHED | TICKET_RATED",
  "occurred_at": "2026-11-18T06:30:00Z",
  "ticket": {
    "id": "019...",
    "ticket_code": "HD-2026-0001",
    "title": "Không kết nối được VPN",
    "status": "NEW",
    "priority": "HIGH",
    "asset_code": "LAP-KD-088"
  },
  "actor": { "username": "nhanvien", "full_name": "Nguyễn Văn An", "role": "END_USER" },
  "summary": "Nhân viên tạo ticket mới",
  "details": {}
}
```

---

## 7. HƯỚNG DẪN CHẠY NHANH (QUICKSTART)

### Cách 1: Docker Compose (Full Stack)
```bash
cp .env.example .env
docker compose up -d --build
```
Truy cập qua Caddy Reverse Proxy: `http://localhost` (hoặc `http://localhost:3000` cho Frontend, `http://localhost:8000/docs` cho Swagger API).

### Cách 2: Chạy Local Dev (Không cần Docker)
- **Backend:**
  ```bash
  cd backend
  pip install -r requirements.txt
  uvicorn app.main:app --reload --port 8000
  ```
- **Frontend:**
  ```bash
  cd frontend
  npm install
  npm run dev
  ```
- Tài khoản test mặc định (mật khẩu `Password123!`): `nhanvien`, `kythuat`, `truongnhom`, `admin`.
