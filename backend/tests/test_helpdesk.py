from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import time
from unittest.mock import patch

import httpx
from httpx import ASGITransport, AsyncClient
import pytest

# Force isolated test SQLite database before importing app modules
TEST_DB_PATH = Path(__file__).resolve().parent / "test_helpdesk.db"
if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["RUN_EMBEDDED_WORKERS"] = "false"
os.environ["LDAP_ENABLED"] = "false"
os.environ["LDAP_ALLOW_LOCAL_FALLBACK"] = "true"
os.environ["MINIO_ENABLED"] = "false"
os.environ["N8N_DRY_RUN"] = "true"
os.environ["AUTO_ASSIGN_ENABLED"] = "false"

from app.core.config import get_settings

get_settings.cache_clear()

from app.core.database import AsyncSessionLocal, Base, engine  # noqa: E402
from app.core.uuid_utils import uuid7  # noqa: E402
from app.main import app  # noqa: E402
from app.models.models import BusinessCalendar, OutboxStatus, Ticket, TicketPriority, TicketStatus, UserRole  # noqa: E402
from app.seed import seed_initial_data  # noqa: E402
from app.services.sla_engine import calculate_due_date  # noqa: E402
from app.workers.outbox_dispatcher import dispatch_pending_outbox_batch  # noqa: E402
from app.workers.sla_scanner import scan_sla_deadlines  # noqa: E402
from sqlalchemy import select  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
async def setup_test_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as db:
        await seed_initial_data(db)
    yield
    await engine.dispose()
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()


async def _login(client: AsyncClient, username: str, password: str = "Password123!") -> str:
    resp = await client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def test_uuid7_time_ordered_and_unique():
    u1 = uuid7()
    time.sleep(0.002)
    u2 = uuid7()
    assert u1.version == 7
    assert u2.version == 7
    assert u1 != u2
    assert str(u1) < str(u2)


def test_sla_business_hours_calculation():
    cal = BusinessCalendar(
        name="Standard",
        timezone="Asia/Ho_Chi_Minh",
        work_days={"0": ["08:00", "17:30"], "1": ["08:00", "17:30"]},
        holidays=[],
        is_default=True,
    )
    # Monday 2026-11-16 17:00 ICT (10:00 UTC) + 60 mins -> Tuesday 08:30 ICT (01:30 UTC)
    start_utc = datetime(2026, 11, 16, 10, 0, tzinfo=timezone.utc)
    due = calculate_due_date(start_utc, 60, cal, business_hours_only=True)
    assert due == datetime(2026, 11, 17, 1, 30, tzinfo=timezone.utc)

    # 24/7 mode ignores calendar
    due_247 = calculate_due_date(start_utc, 60, cal, business_hours_only=False)
    assert due_247 == start_utc + timedelta(minutes=60)


@pytest.mark.asyncio
async def test_ldap_authentication_upsert_and_login():
    mock_ldap_profile = {
        "username": "minh.ldap",
        "full_name": "Nguyễn Hoàng Minh",
        "email": "minh.ldap@company.local",
        "department_name": "Phòng Kế toán",
        "ldap_dn": "CN=Nguyen Hoang Minh,OU=KeToan,DC=company,DC=local",
        "role": UserRole.IT_AGENT,
    }
    settings = get_settings()
    settings.LDAP_ENABLED = True
    try:
        with patch("app.core.security.authenticate_ldap", return_value=mock_ldap_profile):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/auth/login",
                    json={"username": "COMPANY\\minh.ldap", "password": "corp-password"},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["auth_provider"] == "LDAP_AD"
                assert data["user"]["username"] == "minh.ldap"
                assert data["user"]["role"] == "IT_AGENT"
                assert data["user"]["department"]["code"] == "KT"
    finally:
        settings.LDAP_ENABLED = False


@pytest.mark.asyncio
async def test_full_ticket_lifecycle_ctrl_v_sla_pause_rbac_and_workers():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user_token = await _login(client, "nhanvien")
        agent_token = await _login(client, "kythuat")
        lead_token = await _login(client, "truongnhom")
        admin_token = await _login(client, "admin")

        user_headers = {"Authorization": f"Bearer {user_token}"}
        agent_headers = {"Authorization": f"Bearer {agent_token}"}
        lead_headers = {"Authorization": f"Bearer {lead_token}"}
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # 1. Metadata & Ctrl+V Paste image pre-upload
        meta_resp = await client.get("/api/v1/tickets/metadata", headers=user_headers)
        assert meta_resp.status_code == 200
        categories = meta_resp.json()["categories"]
        net_cat = next(c for c in categories if c["slug"] == "network-wifi-vpn")

        pre_resp = await client.post(
            "/api/v1/attachments/presigned-upload",
            headers=user_headers,
            json={"file_name": "screenshot.png", "content_type": "image/png", "size_bytes": 12},
        )
        assert pre_resp.status_code == 200
        att_info = pre_resp.json()
        put_resp = await client.put(
            att_info["direct_upload_url"],
            headers=user_headers,
            content=b"\x89PNG\r\n\x1a\nFAKE",
        )
        assert put_resp.status_code == 200
        assert put_resp.json()["is_uploaded"] is True

        # 2. 10-second Ticket Creation with asset_code & pasted screenshot
        create_resp = await client.post(
            "/api/v1/tickets",
            headers=user_headers,
            json={
                "title": "Lỗi mất mạng LAN ở bàn làm việc",
                "description": "Cắm dây mạng không nhận IP, có đính kèm ảnh chụp màn hình.",
                "category_id": net_cat["id"],
                "asset_code": "pc-kt-099",
                "attachment_ids": [att_info["attachment_id"]],
            },
        )
        assert create_resp.status_code == 201, create_resp.text
        ticket = create_resp.json()
        ticket_id = ticket["id"]
        assert ticket["asset_code"] == "PC-KT-099"
        assert ticket["priority"] == "HIGH"
        assert ticket["status"] == "NEW"
        assert len(ticket["attachments"]) == 1

        # Verify file download works with ?token= query param (for <img> tags)
        dl_resp = await client.get(f"{ticket['attachments'][0]['download_url']}?token={user_token}")
        assert dl_resp.status_code == 200
        assert dl_resp.content.startswith(b"\x89PNG")

        # 3. RBAC check: END_USER cannot claim ticket or post internal note
        forbidden_claim = await client.post(f"/api/v1/tickets/{ticket_id}/claim", headers=user_headers)
        assert forbidden_claim.status_code == 403

        forbidden_internal = await client.post(
            f"/api/v1/tickets/{ticket_id}/comments",
            headers=user_headers,
            json={"body": "Internal attempt", "is_internal": True},
        )
        assert forbidden_internal.status_code == 403

        # 4. IT Agent claims ticket -> IN_PROGRESS + stamps first_responded_at
        claim_resp = await client.post(f"/api/v1/tickets/{ticket_id}/claim", headers=agent_headers)
        assert claim_resp.status_code == 200
        claimed = claim_resp.json()
        assert claimed["status"] == "IN_PROGRESS"
        assert claimed["first_responded_at"] is not None

        # Agent posts internal note (hidden from END_USER)
        note_resp = await client.post(
            f"/api/v1/tickets/{ticket_id}/comments",
            headers=agent_headers,
            json={"body": "Đã kiểm tra port switch phòng KT.", "is_internal": True},
        )
        assert note_resp.status_code == 201

        user_view = (await client.get(f"/api/v1/tickets/{ticket_id}", headers=user_headers)).json()
        assert all(not c["is_internal"] for c in user_view["comments"])

        # 5. Pause SLA via WAITING_FOR_USER, then resume via user reply comment
        due_before = datetime.fromisoformat(claimed["resolution_due_at"])
        pause_resp = await client.patch(
            f"/api/v1/tickets/{ticket_id}/status",
            headers=agent_headers,
            json={"status": "WAITING_FOR_USER", "note": "Bạn chụp giúp mình đèn cổng LAN nhé."},
        )
        assert pause_resp.status_code == 200
        paused_data = pause_resp.json()
        assert paused_data["status"] == "WAITING_FOR_USER"
        assert paused_data["sla_status"]["state"] == "PAUSED"

        # Backdate sla_paused_at by 120 seconds in DB to verify deterministic SLA extension
        async with AsyncSessionLocal() as db:
            t_row = (await db.execute(select(Ticket).where(Ticket.id == ticket_id))).scalar_one()
            t_row.sla_paused_at = datetime.now(timezone.utc) - timedelta(seconds=120)
            await db.commit()

        reply_resp = await client.post(
            f"/api/v1/tickets/{ticket_id}/comments",
            headers=user_headers,
            json={"body": "Đèn LAN nhấp nháy cam rồi ạ.", "is_internal": False},
        )
        assert reply_resp.status_code == 201

        resumed_detail = (await client.get(f"/api/v1/tickets/{ticket_id}", headers=agent_headers)).json()
        assert resumed_detail["status"] == "IN_PROGRESS"
        assert resumed_detail["total_paused_seconds"] >= 119
        due_after = datetime.fromisoformat(resumed_detail["resolution_due_at"])
        assert (due_after - due_before).total_seconds() >= 119

        # 6. Resolve & User Rates + Closes
        resolve_resp = await client.patch(
            f"/api/v1/tickets/{ticket_id}/status",
            headers=agent_headers,
            json={"status": "RESOLVED", "note": "Đã bấm lại đầu hạt mạng."},
        )
        assert resolve_resp.status_code == 200
        assert resolve_resp.json()["status"] == "RESOLVED"

        rate_resp = await client.post(
            f"/api/v1/tickets/{ticket_id}/rate",
            headers=user_headers,
            json={"rating": 5, "feedback": "Xử lý rất nhanh!", "close_ticket": True},
        )
        assert rate_resp.status_code == 200
        assert rate_resp.json()["status"] == "CLOSED"
        assert rate_resp.json()["rating"] == 5

        # 7. Workers: SLA Scanner & Outbox Dispatcher
        async with AsyncSessionLocal() as db:
            # Force one ticket past resolution due to verify SLA breach detection
            t_breach = (
                await db.execute(select(Ticket).where(Ticket.ticket_code == "HD-2026-0001"))
            ).scalar_one()
            t_breach.resolution_due_at = datetime.now(timezone.utc) - timedelta(minutes=5)
            await db.commit()

            scan_res = await scan_sla_deadlines(db)
            assert scan_res["breaches"] >= 1

            dispatched = await dispatch_pending_outbox_batch(db, batch_size=50)
            assert dispatched >= 1

        # 8. Analytics & Admin endpoints
        analytics_resp = await client.get("/api/v1/analytics/summary", headers=lead_headers)
        assert analytics_resp.status_code == 200
        assert analytics_resp.json()["total_tickets"] >= 5

        outbox_resp = await client.get("/api/v1/admin/outbox-events", headers=admin_headers)
        assert outbox_resp.status_code == 200
        assert any(ev["status"] == OutboxStatus.SENT.value for ev in outbox_resp.json())

        # Outbox HTTP retry test when N8N_DRY_RUN=false and webhook returns 500
        settings = get_settings()
        settings.N8N_DRY_RUN = False
        try:
            async with AsyncSessionLocal() as db:
                t_any = (await db.execute(select(Ticket).where(Ticket.ticket_code == "HD-2026-0002"))).scalar_one()
                from app.services.outbox_writer import emit_outbox_event

                ev = emit_outbox_event(db, t_any, None, "TEST_RETRY", "Test failure retry")
                await db.commit()
                ev_id = ev.id

                async def fail_handler(_request):
                    return httpx.Response(500, text="n8n down")

                async with httpx.AsyncClient(transport=httpx.MockTransport(fail_handler)) as mock_http:
                    await dispatch_pending_outbox_batch(db, batch_size=10, http_client=mock_http)

                from app.models.models import OutboxEvent

                refreshed = (await db.execute(select(OutboxEvent).where(OutboxEvent.id == ev_id))).scalar_one()
                assert refreshed.retry_count == 1
                assert refreshed.status == OutboxStatus.PENDING
                assert refreshed.next_retry_at is not None
        finally:
            settings.N8N_DRY_RUN = True


def test_ultraview_parser_patterns():
    from app.services.ultraview_service import extract_ultraview_credentials

    c1 = extract_ultraview_credentials("id 68 412 903 pass 8492")
    assert c1 == {"id": "68412903", "pass": "8492"}

    c2 = extract_ultraview_credentials("Nhờ IT vào ultraview: 68412903 / ab12")
    assert c2 == {"id": "68412903", "pass": "ab12"}

    c3 = extract_ultraview_credentials("uv 123 456 789 mk 9988")
    assert c3 == {"id": "123456789", "pass": "9988"}

    assert extract_ultraview_credentials("Máy in hết mực tầng 2") is None


@pytest.mark.asyncio
async def test_ultraview_request_provide_and_auto_extract():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user_token = await _login(client, "nhanvien")
        agent_token = await _login(client, "kythuat")
        user_headers = {"Authorization": f"Bearer {user_token}"}
        agent_headers = {"Authorization": f"Bearer {agent_token}"}

        # 1. Create ticket with initial UltraViewer credentials
        create_resp = await client.post(
            "/api/v1/tickets",
            headers=user_headers,
            json={
                "title": "Lỗi chữ ký số không nhận token",
                "description": "Nhờ IT hỗ trợ kiểm tra giúp mình.",
                "ultraview_id": "68 412 903",
                "ultraview_pass": "8492",
            },
        )
        assert create_resp.status_code == 201, create_resp.text
        t = create_resp.json()
        tid = t["id"]
        assert t["custom_data"]["ultraview"]["id"] == "68412903"
        assert t["custom_data"]["ultraview"]["pass"] == "8492"
        assert t["custom_data"]["ultraview"]["state"] == "READY"

        # 2. Agent requests UltraViewer -> WAITING_FOR_USER (pauses SLA) & state=REQUESTED
        req_resp = await client.post(f"/api/v1/tickets/{tid}/ultraview/request", headers=agent_headers)
        assert req_resp.status_code == 200, req_resp.text
        req_data = req_resp.json()
        assert req_data["status"] == "WAITING_FOR_USER"
        assert req_data["sla_status"]["is_paused"] is True
        assert req_data["custom_data"]["ultraview"]["state"] == "REQUESTED"

        # 3. User provides UltraViewer -> IN_PROGRESS (resumes SLA) & state=READY
        prov_resp = await client.post(
            f"/api/v1/tickets/{tid}/ultraview/provide",
            headers=user_headers,
            json={"ultraview_id": "68 412 903", "ultraview_pass": "5566"},
        )
        assert prov_resp.status_code == 200, prov_resp.text
        prov_data = prov_resp.json()
        assert prov_data["status"] == "IN_PROGRESS"
        assert prov_data["sla_status"]["is_paused"] is False
        assert prov_data["custom_data"]["ultraview"]["pass"] == "5566"
        assert prov_data["custom_data"]["ultraview"]["state"] == "READY"

        # 4. Auto-extract UltraViewer credentials from regular chat comment
        cmt_resp = await client.post(
            f"/api/v1/tickets/{tid}/comments",
            headers=user_headers,
            json={"body": "Mình mở lại rồi nha id 68412903 pass 7788", "is_internal": False},
        )
        assert cmt_resp.status_code == 201
        detail = (await client.get(f"/api/v1/tickets/{tid}", headers=agent_headers)).json()
        assert detail["custom_data"]["ultraview"]["pass"] == "7788"


@pytest.mark.asyncio
async def test_websocket_rbac_and_handshake():
    from unittest.mock import AsyncMock
    from starlette.testclient import TestClient
    from app.core.ws_manager import ConnectionManager

    # Unit-test RBAC event filtering
    mgr = ConnectionManager()
    ws_it = AsyncMock()
    ws_owner = AsyncMock()
    ws_other_user = AsyncMock()

    await mgr.connect(ws_it, "it-1", UserRole.IT_AGENT)
    await mgr.connect(ws_owner, "user-1", UserRole.END_USER)
    await mgr.connect(ws_other_user, "user-2", UserRole.END_USER)

    await mgr.broadcast_ticket_event("COMMENT_ADDED", "ticket-1", "user-1", is_internal=True)
    ws_it.send_json.assert_awaited_once()
    ws_owner.send_json.assert_not_awaited()
    ws_other_user.send_json.assert_not_awaited()

    ws_it.reset_mock()
    await mgr.broadcast_ticket_event("COMMENT_ADDED", "ticket-1", "user-1", is_internal=False)
    ws_it.send_json.assert_awaited_once()
    ws_owner.send_json.assert_awaited_once()
    ws_other_user.send_json.assert_not_awaited()

    # Live WebSocket handshake + ping/pong via Starlette TestClient
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "nhanvien")

    with TestClient(app) as sync_client:
        with sync_client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
            ws.send_text("ping")
            assert ws.receive_text() == "pong"


@pytest.mark.asyncio
async def test_analytics_filters_and_multi_format_export():
    from io import BytesIO
    from openpyxl import load_workbook

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user_token = await _login(client, "nhanvien")
        lead_token = await _login(client, "truongnhom")
        user_headers = {"Authorization": f"Bearer {user_token}"}
        lead_headers = {"Authorization": f"Bearer {lead_token}"}

        # 1. END_USER forbidden
        forb = await client.get("/api/v1/analytics/export?format=csv", headers=user_headers)
        assert forb.status_code == 403

        # 2. Summary with filters
        today = datetime.now(timezone.utc).date().isoformat()
        sum_resp = await client.get(
            f"/api/v1/analytics/summary?date_from=2026-01-01&date_to={today}",
            headers=lead_headers,
        )
        assert sum_resp.status_code == 200
        s = sum_resp.json()
        assert "by_agent" in s and len(s["by_agent"]) >= 1
        assert "daily_trend" in s and len(s["daily_trend"]) >= 1
        assert "avg_rating" in s

        # 3. Export CSV (UTF-8 BOM + Vietnamese header/data)
        csv_resp = await client.get("/api/v1/analytics/export?format=csv", headers=lead_headers)
        assert csv_resp.status_code == 200
        assert csv_resp.content.startswith(b"\xef\xbb\xbf")
        assert "helpdesk-report-" in csv_resp.headers["content-disposition"]
        assert "Ticket Code,Title,Status" in csv_resp.text

        # 4. Export Excel (.xlsx)
        xlsx_resp = await client.get("/api/v1/analytics/export?format=xlsx", headers=lead_headers)
        assert xlsx_resp.status_code == 200
        assert xlsx_resp.content.startswith(b"PK\x03\x04")
        wb = load_workbook(BytesIO(xlsx_resp.content))
        assert "Summary" in wb.sheetnames
        assert "Tickets" in wb.sheetnames
        assert wb["Tickets"].max_row >= 2

        # 5. Export JSON
        json_resp = await client.get("/api/v1/analytics/export?format=json", headers=lead_headers)
        assert json_resp.status_code == 200
        jdata = json_resp.json()
        assert "summary" in jdata and "tickets" in jdata
        assert len(jdata["tickets"]) >= 4


@pytest.mark.asyncio
async def test_auto_assign_least_loaded():
    settings = get_settings()
    settings.AUTO_ASSIGN_ENABLED = True
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            user_token = await _login(client, "nhanvien")
            user_headers = {"Authorization": f"Bearer {user_token}"}

            meta = (await client.get("/api/v1/tickets/metadata", headers=user_headers)).json()
            l1_cat = next(c for c in meta["categories"] if c["slug"] == "account-email-ad")

            # kythuat has active tickets, truongnhom is lead in grp_l1 with 0 -> picks truongnhom or least-loaded
            resp = await client.post(
                "/api/v1/tickets",
                headers=user_headers,
                json={
                    "title": "Quên mật khẩu tài khoản AD",
                    "description": "Nhờ IT mở khóa giúp tài khoản.",
                    "category_id": l1_cat["id"],
                },
            )
            assert resp.status_code == 201, resp.text
            t = resp.json()
            assert t["status"] == "ASSIGNED"
            assert t["assignee"] is not None
            assert t["first_responded_at"] is not None
    finally:
        settings.AUTO_ASSIGN_ENABLED = False


@pytest.mark.asyncio
async def test_auto_close_stale_resolved():
    from app.workers.sla_scanner import auto_close_stale_resolved_tickets

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        lead_token = await _login(client, "truongnhom")
        lead_headers = {"Authorization": f"Bearer {lead_token}"}

        async with AsyncSessionLocal() as db:
            t = (
                await db.execute(select(Ticket).where(Ticket.ticket_code == "HD-2026-0004"))
            ).scalar_one()
            t.status = TicketStatus.RESOLVED
            t.resolved_at = datetime.now(timezone.utc) - timedelta(hours=72)
            t.closed_at = None
            await db.commit()

            closed_count = await auto_close_stale_resolved_tickets(db, max_age_hours=48)
            assert closed_count >= 1

        detail = (await client.get(f"/api/v1/tickets/{t.id}", headers=lead_headers)).json()
        assert detail["status"] == "CLOSED"
        assert detail["closed_at"] is not None


@pytest.mark.asyncio
async def test_knowledge_base_seeded_and_admin_crud():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user_token = await _login(client, "nhanvien")
        lead_token = await _login(client, "truongnhom")
        user_headers = {"Authorization": f"Bearer {user_token}"}
        lead_headers = {"Authorization": f"Bearer {lead_token}"}

        meta = (await client.get("/api/v1/tickets/metadata", headers=user_headers)).json()
        net_cat = next(c for c in meta["categories"] if c["slug"] == "network-wifi-vpn")
        assert len(net_cat["form_schema"]["kb_articles"]) >= 2

        add_resp = await client.post(
            f"/api/v1/admin/categories/{net_cat['id']}/kb",
            headers=lead_headers,
            json={
                "title": "Test KB Article",
                "keywords": ["test", "kb"],
                "steps": ["Step 1", "Step 2"],
            },
        )
        assert add_resp.status_code == 201
        added_articles = add_resp.json()["form_schema"]["kb_articles"]
        new_id = added_articles[-1]["id"]

        del_resp = await client.delete(
            f"/api/v1/admin/categories/{net_cat['id']}/kb/{new_id}",
            headers=lead_headers,
        )
        assert del_resp.status_code == 200
        assert all(a["id"] != new_id for a in del_resp.json()["form_schema"]["kb_articles"])


@pytest.mark.asyncio
async def test_dedicated_kb_articles_with_images_and_rbac():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user_token = await _login(client, "nhanvien")
        agent_token = await _login(client, "kythuat")
        user_headers = {"Authorization": f"Bearer {user_token}"}
        agent_headers = {"Authorization": f"Bearer {agent_token}"}

        # 1. Seeded internal + public articles exist for IT_AGENT, END_USER only sees PUBLIC
        it_list = (await client.get("/api/v1/kb", headers=agent_headers)).json()
        user_list = (await client.get("/api/v1/kb", headers=user_headers)).json()
        assert any(a["visibility"] == "INTERNAL" for a in it_list["items"])
        assert all(a["visibility"] == "PUBLIC" for a in user_list["items"])

        # 2. IT_AGENT uploads a screenshot and creates an INTERNAL runbook article
        presigned = (
            await client.post(
                "/api/v1/attachments/presigned-upload",
                headers=agent_headers,
                json={"file_name": "fix-spooler.png", "content_type": "image/png", "size_bytes": 12},
            )
        ).json()
        put_resp = await client.put(
            presigned["direct_upload_url"],
            headers={**agent_headers, "Content-Type": "image/png"},
            content=b"\x89PNG\r\n\x1a\nfake",
        )
        assert put_resp.status_code == 200
        att_id = put_resp.json()["id"]

        create_resp = await client.post(
            "/api/v1/kb",
            headers=agent_headers,
            json={
                "title": "Fix lỗi ERP ca khó 0x800",
                "visibility": "INTERNAL",
                "symptoms": "Mở ERP báo lỗi kết nối SQL.",
                "root_cause": "Firewall chặn port 1433.",
                "steps": ["Mở port 1433", "Restart service"],
                "notes": "Test-NetConnection -Port 1433",
                "keywords": ["erp", "0x800"],
                "attachment_ids": [att_id],
            },
        )
        assert create_resp.status_code == 201, create_resp.text
        created = create_resp.json()
        assert len(created["attachments"]) == 1
        kb_id = created["id"]

        # 3. END_USER cannot read INTERNAL KB article or its image attachment
        assert (await client.get(f"/api/v1/kb/{kb_id}", headers=user_headers)).status_code == 403
        assert (
            await client.get(f"/api/v1/attachments/{att_id}/file", headers=user_headers)
        ).status_code == 403

        # 4. IT_AGENT can update and switch to PUBLIC, then END_USER can read it
        patch_resp = await client.patch(
            f"/api/v1/kb/{kb_id}",
            headers=agent_headers,
            json={"visibility": "PUBLIC", "title": "Fix lỗi ERP ca khó 0x800 (Updated)"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["visibility"] == "PUBLIC"
        assert (await client.get(f"/api/v1/kb/{kb_id}", headers=user_headers)).status_code == 200
        assert (
            await client.get(f"/api/v1/attachments/{att_id}/file", headers=user_headers)
        ).status_code == 200

        # 5. Cleanup delete
        del_resp = await client.delete(f"/api/v1/kb/{kb_id}", headers=agent_headers)
        assert del_resp.status_code == 204
