# IT Helpdesk System (Internal Portal & IT Workspace)

Cổng tiếp nhận và xử lý sự cố IT nội bộ (Helpdesk) tối giản cho nhân viên (`10s` tạo xong ticket, hỗ trợ dán ảnh `Ctrl+V`), chặt chẽ về SLA & State Machine cho đội ngũ IT, xác thực tập trung qua **LDAP / Active Directory**, tách biệt với hệ thống tài sản (liên kết qua `asset_code`), và đảm bảo gửi thông báo tin cậy qua **Transactional Outbox Pattern -> n8n**.

> Xem tài liệu kiến trúc chi tiết tại [New Text Document.md](./New%20Text%20Document.md).

## Kiến trúc tổng thể
- **Frontend:** Next.js (App Router) + TypeScript + Tailwind CSS + Lucide Icons
- **Backend API:** Python + FastAPI + SQLAlchemy 2.0 (Async) + Alembic + `UUIDv7`
- **Database:** PostgreSQL 16 (hỗ trợ SQLite async cho chạy thử nghiệm/test nhanh không cần Docker)
- **Object Storage:** MinIO (S3 Presigned URLs + API upload proxy fallback)
- **Authentication:** Corporate **LDAP / Active Directory** (`ldap3`) + JWT (`HS256`) với 4 vai trò: `END_USER`, `IT_AGENT`, `IT_LEAD`, `SYS_ADMIN`
- **Background Workers:** `Outbox Dispatcher` (gửi webhook HMAC sang n8n) & `SLA Scanner` (`SELECT ... FOR UPDATE SKIP LOCKED`)
- **Reverse Proxy:** Caddy

## Cấu hình LDAP / Active Directory
Trong `.env`:
- Đặt `LDAP_ENABLED=true` khi kết nối vào Domain Controller công ty.
- Cấu hình `LDAP_SERVER_URI`, `LDAP_DOMAIN`, `LDAP_BASE_DN`, `LDAP_USER_DN_TEMPLATE`, `LDAP_SEARCH_FILTER`.
- Khi `LDAP_ALLOW_LOCAL_FALLBACK=true` (mặc định bật ở dev), có thể đăng nhập bằng tài khoản nội bộ trong DB (`nhanvien`, `kythuat`, `truongnhom`, `admin` — mật khẩu mặc định `Password123!`).

## Chạy dự án

### Cách 1: Chạy dev local (khuyên dùng khi đang code — nhanh, có hot-reload)
Mở **2 cửa sổ terminal (PowerShell)**:

1. **Terminal 1 — Backend (FastAPI):**
```powershell
cd backend
.\.venv\Scripts\uvicorn.exe app.main:app --reload --port 8000
```
*(Hoặc activate trước: `.\.venv\Scripts\Activate.ps1` rồi chạy `uvicorn app.main:app --reload --port 8000`)*

2. **Terminal 2 — Frontend (Next.js):**
```powershell
cd frontend
npm run dev
```

- Web Portal / Workspace: `http://localhost:3000`
- FastAPI Swagger UI: `http://localhost:8000/docs`
- *(Lưu ý: nếu trước đó có chạy Docker thì chạy `docker compose down` để nhả cổng `8000` và `3000`.)*

### Cách 2: Chạy toàn bộ bằng Docker Compose (test giống môi trường thật / deploy)
*(Nhớ mở **Docker Desktop** trước khi chạy)*

```powershell
# Tạo .env nếu chưa có
cp .env.example .env

# Lần đầu chạy hoặc khi vừa sửa code / dependencies:
docker compose up -d --build

# Các lần sau (không sửa code):
docker compose up -d

# Dừng container (giữ nguyên dữ liệu DB & MinIO):
docker compose down
```
- Web Portal / Workspace: `http://localhost`
- FastAPI Swagger UI: `http://localhost/docs`
- MinIO Console: `http://localhost:9001`
