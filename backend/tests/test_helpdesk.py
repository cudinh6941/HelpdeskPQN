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
            assert t["first_responded_at"] is None

            assignee_username = t["assignee"]["username"]
            agent_token = await _login(client, assignee_username)
            agent_headers = {"Authorization": f"Bearer {agent_token}"}
            cmt_resp = await client.post(
                f"/api/v1/tickets/{t['id']}/comments",
                headers=agent_headers,
                json={"body": "Mình đã tiếp nhận và đang kiểm tra giúp bạn.", "is_internal": False},
            )
            assert cmt_resp.status_code == 201
            updated_ticket = (
                await client.get(f"/api/v1/tickets/{t['id']}", headers=agent_headers)
            ).json()
            assert updated_ticket["first_responded_at"] is not None
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


@pytest.mark.asyncio
async def test_automation_settings_persisted_in_db():
    from app.models.models import SystemSetting
    from app.services.settings_service import KEY_AUTO_ASSIGN_ENABLED, KEY_AUTO_CLOSE_RESOLVED_HOURS
    from app.workers.sla_scanner import auto_close_stale_resolved_tickets
    from sqlalchemy import delete

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        lead_token = await _login(client, "truongnhom")
        lead_headers = {"Authorization": f"Bearer {lead_token}"}

        try:
            patch_resp = await client.patch(
                "/api/v1/admin/automation-settings",
                headers=lead_headers,
                json={"auto_assign_enabled": True, "auto_close_resolved_hours": 72},
            )
            assert patch_resp.status_code == 200
            assert patch_resp.json() == {
                "auto_assign_enabled": True,
                "auto_close_resolved_hours": 72,
            }

            # Even if runtime settings cache resets, GET reads persisted values from DB
            get_settings.cache_clear()
            get_resp = await client.get("/api/v1/admin/automation-settings", headers=lead_headers)
            assert get_resp.status_code == 200
            assert get_resp.json() == {
                "auto_assign_enabled": True,
                "auto_close_resolved_hours": 72,
            }

            async with AsyncSessionLocal() as db:
                t = (
                    await db.execute(select(Ticket).where(Ticket.ticket_code == "HD-2026-0004"))
                ).scalar_one()
                t.status = TicketStatus.RESOLVED
                t.resolved_at = datetime.now(timezone.utc) - timedelta(hours=60)
                t.closed_at = None
                await db.commit()

                # Threshold in DB is 72h -> ticket resolved 60h ago stays RESOLVED
                assert await auto_close_stale_resolved_tickets(db) == 0

            # Lower threshold in DB to 48h -> scanner worker picks up DB setting and closes it
            patch2 = await client.patch(
                "/api/v1/admin/automation-settings",
                headers=lead_headers,
                json={"auto_close_resolved_hours": 48},
            )
            assert patch2.status_code == 200

            async with AsyncSessionLocal() as db:
                assert await auto_close_stale_resolved_tickets(db) >= 1
        finally:
            async with AsyncSessionLocal() as db:
                await db.execute(
                    delete(SystemSetting).where(
                        SystemSetting.key.in_(
                            [KEY_AUTO_ASSIGN_ENABLED, KEY_AUTO_CLOSE_RESOLVED_HOURS]
                        )
                    )
                )
                await db.commit()
            get_settings.cache_clear()
            get_settings().AUTO_ASSIGN_ENABLED = False


@pytest.mark.asyncio
async def test_attachment_upload_validation_and_orphan_cleanup():
    from app.core.minio_client import storage_service
    from app.models.models import TicketAttachment
    from app.workers.sla_scanner import cleanup_orphan_attachments

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user_token = await _login(client, "nhanvien")
        user_headers = {"Authorization": f"Bearer {user_token}"}

        # 1. Blocked MIME / dangerous extensions rejected with 400
        svg_resp = await client.post(
            "/api/v1/attachments/presigned-upload",
            headers=user_headers,
            json={"file_name": "evil.svg", "content_type": "image/svg+xml", "size_bytes": 64},
        )
        assert svg_resp.status_code == 400

        html_resp = await client.post(
            "/api/v1/attachments/presigned-upload",
            headers=user_headers,
            json={"file_name": "payload.html", "content_type": "text/html", "size_bytes": 64},
        )
        assert html_resp.status_code == 400

        # 2. Oversized file rejected with 413 on metadata and actual upload
        max_bytes = get_settings().ATTACHMENT_MAX_BYTES
        big_meta = await client.post(
            "/api/v1/attachments/presigned-upload",
            headers=user_headers,
            json={"file_name": "big.png", "content_type": "image/png", "size_bytes": max_bytes + 1},
        )
        assert big_meta.status_code == 413

        valid_pre = await client.post(
            "/api/v1/attachments/presigned-upload",
            headers=user_headers,
            json={"file_name": "probe.png", "content_type": "image/png", "size_bytes": 10},
        )
        assert valid_pre.status_code == 200
        big_put = await client.put(
            valid_pre.json()["direct_upload_url"],
            headers={**user_headers, "Content-Type": "image/png"},
            content=b"x" * (max_bytes + 1),
        )
        assert big_put.status_code == 413

        # 3. Safe inline PNG vs forced-download TXT + X-Content-Type-Options: nosniff
        png_pre = await client.post(
            "/api/v1/attachments/presigned-upload",
            headers=user_headers,
            json={"file_name": "ok.png", "content_type": "image/png", "size_bytes": 12},
        )
        png_put = await client.put(
            png_pre.json()["direct_upload_url"],
            headers={**user_headers, "Content-Type": "image/png"},
            content=b"\x89PNG\r\n\x1a\nOK!!",
        )
        assert png_put.status_code == 200
        png_dl = await client.get(png_put.json()["download_url"], headers=user_headers)
        assert png_dl.status_code == 200
        assert png_dl.headers["content-disposition"].startswith("inline;")
        assert png_dl.headers["x-content-type-options"] == "nosniff"

        txt_pre = await client.post(
            "/api/v1/attachments/presigned-upload",
            headers=user_headers,
            json={"file_name": "debug.txt", "content_type": "text/plain", "size_bytes": 9},
        )
        txt_put = await client.put(
            txt_pre.json()["direct_upload_url"],
            headers={**user_headers, "Content-Type": "text/plain"},
            content=b"hello log",
        )
        assert txt_put.status_code == 200
        txt_dl = await client.get(txt_put.json()["download_url"], headers=user_headers)
        assert txt_dl.status_code == 200
        assert txt_dl.headers["content-disposition"].startswith("attachment;")
        assert txt_dl.headers["x-content-type-options"] == "nosniff"

        # 4. Orphan attachment cleanup removes old unattached records & files, keeps recent ones
        orphan_id = png_put.json()["id"]
        recent_id = txt_put.json()["id"]
        async with AsyncSessionLocal() as db:
            old_att = (
                await db.execute(select(TicketAttachment).where(TicketAttachment.id == orphan_id))
            ).scalar_one()
            old_key = old_att.object_key
            old_att.created_at = datetime.now(timezone.utc) - timedelta(hours=48)
            await db.commit()

            assert storage_service.get_object_bytes(old_key) is not None
            cleaned = await cleanup_orphan_attachments(db)
            assert cleaned >= 1
            assert storage_service.get_object_bytes(old_key) is None
            assert (
                await db.execute(select(TicketAttachment).where(TicketAttachment.id == orphan_id))
            ).scalar_one_or_none() is None
            assert (
                await db.execute(select(TicketAttachment).where(TicketAttachment.id == recent_id))
            ).scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_login_rate_limiting():
    from app.core.rate_limit import login_rate_limiter

    login_rate_limiter.reset()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for _ in range(get_settings().LOGIN_RATE_LIMIT_MAX_ATTEMPTS):
                resp = await client.post(
                    "/api/v1/auth/login",
                    json={"username": "ratelimit_probe", "password": "wrong-password"},
                )
                assert resp.status_code == 401

            blocked = await client.post(
                "/api/v1/auth/login",
                json={"username": "ratelimit_probe", "password": "wrong-password"},
            )
            assert blocked.status_code == 429
            assert "retry-after" in {k.lower() for k in blocked.headers.keys()}
    finally:
        login_rate_limiter.reset()


@pytest.mark.asyncio
async def test_scoped_tokens_for_ws_and_media():
    from starlette.testclient import TestClient

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user_token = await _login(client, "nhanvien")
        user_headers = {"Authorization": f"Bearer {user_token}"}

        media_tok_resp = await client.post(
            "/api/v1/auth/scoped-token",
            headers=user_headers,
            json={"scope": "media"},
        )
        assert media_tok_resp.status_code == 200
        media_token = media_tok_resp.json()["token"]

        ws_tok_resp = await client.post(
            "/api/v1/auth/scoped-token",
            headers=user_headers,
            json={"scope": "ws"},
        )
        assert ws_tok_resp.status_code == 200
        ws_token = ws_tok_resp.json()["token"]

        # Scoped tokens must NOT be accepted on general REST endpoints
        assert (
            await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {media_token}"})
        ).status_code == 401
        assert (
            await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {ws_token}"})
        ).status_code == 401

        # Upload an attachment and test scoped token access
        pre = await client.post(
            "/api/v1/attachments/presigned-upload",
            headers=user_headers,
            json={"file_name": "scoped.png", "content_type": "image/png", "size_bytes": 12},
        )
        put = await client.put(
            pre.json()["direct_upload_url"],
            headers={**user_headers, "Content-Type": "image/png"},
            content=b"\x89PNG\r\n\x1a\nTEST",
        )
        assert put.status_code == 200
        dl_url = put.json()["download_url"]

        assert (await client.get(f"{dl_url}?token={ws_token}")).status_code == 401
        assert (await client.get(f"{dl_url}?token={media_token}")).status_code == 200

    with TestClient(app) as sync_client:
        with sync_client.websocket_connect(f"/api/v1/ws?token={ws_token}") as ws:
            ws.send_text("ping")
            assert ws.receive_text() == "pong"

        with pytest.raises(Exception):
            with sync_client.websocket_connect(f"/api/v1/ws?token={media_token}") as ws:
                ws.send_text("ping")


@pytest.mark.asyncio
async def test_admin_groups_members_calendar_departments_and_user_profile():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        lead_token = await _login(client, "truongnhom")
        admin_token = await _login(client, "admin")
        user_token = await _login(client, "nhanvien")

        lead_headers = {"Authorization": f"Bearer {lead_token}"}
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        user_headers = {"Authorization": f"Bearer {user_token}"}

        # 1. Support groups & members management
        groups_resp = await client.get("/api/v1/admin/support-groups", headers=lead_headers)
        assert groups_resp.status_code == 200
        groups = groups_resp.json()
        assert len(groups) >= 1
        target_group_id = groups[0]["id"]

        users_resp = await client.get("/api/v1/admin/users", headers=lead_headers)
        assert users_resp.status_code == 200
        kythuat_user = next(u for u in users_resp.json() if u["username"] == "kythuat")

        add_m = await client.post(
            f"/api/v1/admin/support-groups/{target_group_id}/members",
            headers=lead_headers,
            json={"user_id": kythuat_user["id"], "is_lead": True},
        )
        assert add_m.status_code == 200
        assert any(
            m["user_id"] == kythuat_user["id"] and m["is_lead"] is True
            for m in add_m.json()["members"]
        )

        del_m = await client.delete(
            f"/api/v1/admin/support-groups/{target_group_id}/members/{kythuat_user['id']}",
            headers=lead_headers,
        )
        assert del_m.status_code == 200
        assert all(m["user_id"] != kythuat_user["id"] for m in del_m.json()["members"])

        # 2. Business Calendar GET/PATCH & validation
        cal_get = await client.get("/api/v1/admin/business-calendar", headers=lead_headers)
        assert cal_get.status_code == 200
        orig_cal = cal_get.json()

        bad_cal = await client.patch(
            "/api/v1/admin/business-calendar",
            headers=lead_headers,
            json={"work_days": {"0": ["18:00", "08:00"]}},
        )
        assert bad_cal.status_code == 400

        bad_holiday = await client.patch(
            "/api/v1/admin/business-calendar",
            headers=lead_headers,
            json={"holidays": ["not-a-date"]},
        )
        assert bad_holiday.status_code == 400

        upd_cal = await client.patch(
            "/api/v1/admin/business-calendar",
            headers=lead_headers,
            json={"holidays": ["2026-12-25", "2026-01-01"]},
        )
        assert upd_cal.status_code == 200
        assert upd_cal.json()["holidays"] == ["2026-01-01", "2026-12-25"]

        # Restore original holidays
        await client.patch(
            "/api/v1/admin/business-calendar",
            headers=lead_headers,
            json={"holidays": orig_cal["holidays"]},
        )

        # 3. Departments CRUD
        dept_create = await client.post(
            "/api/v1/admin/departments",
            headers=lead_headers,
            json={"code": "QA_TEST", "name": "Phòng QA Kiểm Thử"},
        )
        assert dept_create.status_code == 201
        dept_id = dept_create.json()["id"]

        dept_patch = await client.patch(
            f"/api/v1/admin/departments/{dept_id}",
            headers=lead_headers,
            json={"name": "Phòng QA Cập Nhật", "is_active": False},
        )
        assert dept_patch.status_code == 200
        assert dept_patch.json()["is_active"] is False

        # 4. Admin Create User, Update User, and Self-Service Profile PATCH /auth/me
        u_create = await client.post(
            "/api/v1/admin/users",
            headers=admin_headers,
            json={
                "username": "local.tester",
                "email": "local.tester@company.local",
                "full_name": "Local Tester",
                "password": "Password123!",
                "role": "IT_AGENT",
                "department_id": dept_id,
                "telegram_chat_id": "tg_999",
            },
        )
        assert u_create.status_code == 201, u_create.text
        created_uid = u_create.json()["id"]
        assert u_create.json()["telegram_chat_id"] == "tg_999"

        u_patch = await client.patch(
            f"/api/v1/admin/users/{created_uid}",
            headers=admin_headers,
            json={"zalo_user_id": "zalo_777", "is_active": False},
        )
        assert u_patch.status_code == 200
        assert u_patch.json()["zalo_user_id"] == "zalo_777"
        assert u_patch.json()["is_active"] is False

        me_patch = await client.patch(
            "/api/v1/auth/me",
            headers=user_headers,
            json={"telegram_chat_id": "11223344", "zalo_user_id": "zalo_nv1"},
        )
        assert me_patch.status_code == 200
        assert me_patch.json()["telegram_chat_id"] == "11223344"
        assert me_patch.json()["zalo_user_id"] == "zalo_nv1"


@pytest.mark.asyncio
async def test_in_app_notifications_lifecycle():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user_token = await _login(client, "nhanvien")
        agent_token = await _login(client, "kythuat")
        user_headers = {"Authorization": f"Bearer {user_token}"}
        agent_headers = {"Authorization": f"Bearer {agent_token}"}

        # Create ticket as nhanvien -> notifies IT
        t_resp = await client.post(
            "/api/v1/tickets",
            headers=user_headers,
            json={
                "title": "Test notification inbox flow",
                "description": "Kiểm tra thông báo trong ứng dụng.",
            },
        )
        assert t_resp.status_code == 201
        tid = t_resp.json()["id"]

        it_notifs = (await client.get("/api/v1/notifications", headers=agent_headers)).json()
        assert it_notifs["unread_count"] >= 1
        assert any(n["ticket_id"] == tid for n in it_notifs["items"])

        # Clear IT unread count, then requester sends a message on unassigned ticket -> IT must be notified
        await client.post("/api/v1/notifications/read-all", headers=agent_headers)
        user_msg_resp = await client.post(
            f"/api/v1/tickets/{tid}/comments",
            headers=user_headers,
            json={"body": "Mình bổ sung thêm thông tin lỗi nhé.", "is_internal": False},
        )
        assert user_msg_resp.status_code == 201
        it_after_msg = (await client.get("/api/v1/notifications", headers=agent_headers)).json()
        assert it_after_msg["unread_count"] >= 1
        assert any(
            n["ticket_id"] == tid and n["event_type"] == "COMMENT_ADDED"
            for n in it_after_msg["items"]
        )

        # Clear nhanvien unread count first
        await client.post("/api/v1/notifications/read-all", headers=user_headers)

        # Internal note must NOT notify END_USER requester
        note_resp = await client.post(
            f"/api/v1/tickets/{tid}/comments",
            headers=agent_headers,
            json={"body": "Internal note hidden from user", "is_internal": True},
        )
        assert note_resp.status_code == 201
        user_after_internal = (await client.get("/api/v1/notifications", headers=user_headers)).json()
        assert user_after_internal["unread_count"] == 0

        # Public reply notifies END_USER requester
        pub_resp = await client.post(
            f"/api/v1/tickets/{tid}/comments",
            headers=agent_headers,
            json={"body": "Public reply visible to user", "is_internal": False},
        )
        assert pub_resp.status_code == 201
        user_after_pub = (await client.get("/api/v1/notifications", headers=user_headers)).json()
        assert user_after_pub["unread_count"] >= 1
        target_notif = next(n for n in user_after_pub["items"] if n["ticket_id"] == tid and not n["is_read"])

        # Mark single read
        read_one = await client.post(
            f"/api/v1/notifications/{target_notif['id']}/read",
            headers=user_headers,
        )
        assert read_one.status_code == 200
        assert read_one.json()["is_read"] is True

        # Mark all read
        read_all = await client.post("/api/v1/notifications/read-all", headers=user_headers)
        assert read_all.status_code == 200
        final_notifs = (await client.get("/api/v1/notifications", headers=user_headers)).json()
        assert final_notifs["unread_count"] == 0


@pytest.mark.asyncio
async def test_queue_filters_pagination_and_bulk_actions():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user_token = await _login(client, "nhanvien")
        agent_token = await _login(client, "kythuat")
        user_headers = {"Authorization": f"Bearer {user_token}"}
        agent_headers = {"Authorization": f"Bearer {agent_token}"}

        meta = (await client.get("/api/v1/tickets/metadata", headers=agent_headers)).json()
        cat_id = meta["categories"][0]["id"]
        today = datetime.now(timezone.utc).date().isoformat()

        # Create 2 fresh tickets
        created_ids: list[str] = []
        for idx in range(2):
            resp = await client.post(
                "/api/v1/tickets",
                headers=user_headers,
                json={
                    "title": f"Bulk queue test ticket {idx}",
                    "description": "Testing queue filters, pagination, and bulk action.",
                    "category_id": cat_id,
                },
            )
            assert resp.status_code == 201
            created_ids.append(resp.json()["id"])

        # Pagination + category + date filters
        page1 = (
            await client.get(
                f"/api/v1/tickets?category_id={cat_id}&date_from={today}&date_to={today}&limit=1&offset=0",
                headers=agent_headers,
            )
        ).json()
        page2 = (
            await client.get(
                f"/api/v1/tickets?category_id={cat_id}&date_from={today}&date_to={today}&limit=1&offset=1",
                headers=agent_headers,
            )
        ).json()
        assert page1["total"] >= 2
        assert len(page1["items"]) == 1
        assert len(page2["items"]) == 1
        assert page1["items"][0]["id"] != page2["items"][0]["id"]

        # Bulk claim
        bulk_claim = await client.post(
            "/api/v1/tickets/bulk",
            headers=agent_headers,
            json={"ticket_ids": created_ids, "action": "claim"},
        )
        assert bulk_claim.status_code == 200
        assert bulk_claim.json()["updated"] == 2

        # Bulk priority update
        bulk_prio = await client.post(
            "/api/v1/tickets/bulk",
            headers=agent_headers,
            json={"ticket_ids": created_ids, "action": "priority", "priority": "CRITICAL"},
        )
        assert bulk_prio.status_code == 200
        assert bulk_prio.json()["updated"] == 2

        # Close first ticket, then attempt bulk RESOLVED -> 1 updated, 1 skipped
        await client.patch(
            f"/api/v1/tickets/{created_ids[0]}/status",
            headers=agent_headers,
            json={"status": "RESOLVED"},
        )
        await client.patch(
            f"/api/v1/tickets/{created_ids[0]}/status",
            headers=user_headers,
            json={"status": "CLOSED"},
        )

        bulk_resolve = await client.post(
            "/api/v1/tickets/bulk",
            headers=agent_headers,
            json={"ticket_ids": created_ids, "action": "status", "status": "RESOLVED"},
        )
        assert bulk_resolve.status_code == 200
        assert bulk_resolve.json()["updated"] == 1
        assert bulk_resolve.json()["skipped"] == 1


@pytest.mark.asyncio
async def test_walkup_ticket_creation_and_property_editing():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user_token = await _login(client, "nhanvien")
        agent_token = await _login(client, "kythuat")
        user_headers = {"Authorization": f"Bearer {user_token}"}
        agent_headers = {"Authorization": f"Bearer {agent_token}"}

        meta = (await client.get("/api/v1/tickets/metadata", headers=agent_headers)).json()
        assert len(meta["requesters"]) >= 4
        nv_user = next(u for u in meta["requesters"] if u["username"] == "nhanvien")
        cat_alt = meta["categories"][1]

        # END_USER cannot create ticket on behalf of another user
        other_user = next(u for u in meta["requesters"] if u["username"] != "nhanvien")
        forb = await client.post(
            "/api/v1/tickets",
            headers=user_headers,
            json={
                "title": "Forbidden walkup",
                "description": "Trying to impersonate.",
                "requester_id": other_user["id"],
            },
        )
        assert forb.status_code == 403

        # IT_AGENT creates walk-up ticket on behalf of nhanvien & assigns to self
        walkup = await client.post(
            "/api/v1/tickets",
            headers=agent_headers,
            json={
                "title": "Hỗ trợ cài máy in qua điện thoại",
                "description": "Nhân viên gọi nội bộ nhờ cài driver máy in.",
                "requester_id": nv_user["id"],
                "assign_to_me": True,
                "asset_code": "pc-kd-101",
            },
        )
        assert walkup.status_code == 201, walkup.text
        w_data = walkup.json()
        assert w_data["requester"]["username"] == "nhanvien"
        assert w_data["assignee"]["username"] == "kythuat"
        assert w_data["status"] == "IN_PROGRESS"
        assert w_data["first_responded_at"] is not None

        # requested_by_me=true for IT_AGENT excludes tickets assigned to IT but requested by others
        my_portal_tickets = (
            await client.get("/api/v1/tickets?requested_by_me=true&limit=50", headers=agent_headers)
        ).json()
        assert all(item["requester"]["username"] == "kythuat" for item in my_portal_tickets["items"])
        assert all(item["id"] != w_data["id"] for item in my_portal_tickets["items"])

        # PATCH ticket category and asset_code
        patched = await client.patch(
            f"/api/v1/tickets/{w_data['id']}",
            headers=agent_headers,
            json={"category_id": cat_alt["id"], "asset_code": "lap-kd-202"},
        )
        assert patched.status_code == 200
        assert patched.json()["category_id"] == cat_alt["id"]
        assert patched.json()["asset_code"] == "LAP-KD-202"


@pytest.mark.asyncio
async def test_related_history_parent_cascade_resolve_and_merge():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user_token = await _login(client, "nhanvien")
        agent_token = await _login(client, "kythuat")
        user_headers = {"Authorization": f"Bearer {user_token}"}
        agent_headers = {"Authorization": f"Bearer {agent_token}"}

        # Create parent incident, child 1 (for cascade resolve), child 2 (for merge)
        parent = (
            await client.post(
                "/api/v1/tickets",
                headers=agent_headers,
                json={
                    "title": "Sự cố mất mạng toàn bộ tầng 3",
                    "description": "Switch core tầng 3 treo.",
                    "asset_code": "SW-T3-01",
                    "assign_to_me": True,
                },
            )
        ).json()
        child1 = (
            await client.post(
                "/api/v1/tickets",
                headers=user_headers,
                json={
                    "title": "Máy kế toán mất mạng",
                    "description": "Không vào được ERP.",
                    "asset_code": "SW-T3-01",
                },
            )
        ).json()
        child2 = (
            await client.post(
                "/api/v1/tickets",
                headers=user_headers,
                json={
                    "title": "Máy kế toán mất mạng (trùng)",
                    "description": "Gửi nhầm lần 2.",
                    "asset_code": "SW-T3-01",
                },
            )
        ).json()

        # Link child1 -> parent
        link_resp = await client.post(
            f"/api/v1/tickets/{child1['id']}/link-parent",
            headers=agent_headers,
            json={"parent_ticket_id": parent["id"]},
        )
        assert link_resp.status_code == 200
        assert link_resp.json()["parent_ticket_id"] == parent["id"]

        # Related endpoint on parent shows by_asset, by_requester, and children
        rel = (await client.get(f"/api/v1/tickets/{parent['id']}/related", headers=agent_headers)).json()
        assert len(rel["by_asset"]) >= 2
        assert any(c["id"] == child1["id"] for c in rel["children"])

        # Resolve parent -> cascades RESOLVED to child1
        res_parent = await client.patch(
            f"/api/v1/tickets/{parent['id']}/status",
            headers=agent_headers,
            json={"status": "RESOLVED", "note": "Đã khởi động lại switch tầng 3."},
        )
        assert res_parent.status_code == 200
        child1_after = (
            await client.get(f"/api/v1/tickets/{child1['id']}", headers=agent_headers)
        ).json()
        assert child1_after["status"] == "RESOLVED"
        assert any(parent["ticket_code"] in c["body"] for c in child1_after["comments"])

        # Merge child2 into another open target (create a fresh open target)
        target = (
            await client.post(
                "/api/v1/tickets",
                headers=agent_headers,
                json={
                    "title": "Ticket chính xử lý mạng tầng 3",
                    "description": "Theo dõi tập trung.",
                    "assign_to_me": True,
                },
            )
        ).json()
        merge_resp = await client.post(
            f"/api/v1/tickets/{child2['id']}/merge",
            headers=agent_headers,
            json={"target_ticket_id": target["id"], "note": "Trùng sự cố"},
        )
        assert merge_resp.status_code == 200
        assert merge_resp.json()["status"] == "CLOSED"
        assert merge_resp.json()["parent_ticket_id"] == target["id"]

        target_detail = (
            await client.get(f"/api/v1/tickets/{target['id']}", headers=agent_headers)
        ).json()
        assert any(
            c["is_internal"] and child2["ticket_code"] in c["body"]
            for c in target_detail["comments"]
        )


@pytest.mark.asyncio
async def test_canned_responses_macros_crud():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user_token = await _login(client, "nhanvien")
        agent_token = await _login(client, "kythuat")
        user_headers = {"Authorization": f"Bearer {user_token}"}
        agent_headers = {"Authorization": f"Bearer {agent_token}"}

        # END_USER cannot access macros
        assert (await client.get("/api/v1/macros", headers=user_headers)).status_code == 403

        # Default seeded macros exist
        macros_list = (await client.get("/api/v1/macros", headers=agent_headers)).json()
        assert any(m["shortcut"] == "uv" for m in macros_list)

        # Create custom macro
        create_resp = await client.post(
            "/api/v1/macros",
            headers=agent_headers,
            json={
                "shortcut": "/vpn_reset",
                "title": "Hướng dẫn reset FortiClient",
                "body": "Vui lòng đăng xuất FortiClient và đăng nhập lại.",
                "target_status": "WAITING_FOR_USER",
                "is_internal": False,
            },
        )
        assert create_resp.status_code == 201
        created = create_resp.json()
        assert created["shortcut"] == "vpn_reset"

        # Duplicate shortcut rejected with 400
        dup_resp = await client.post(
            "/api/v1/macros",
            headers=agent_headers,
            json={
                "shortcut": "vpn_reset",
                "title": "Dup",
                "body": "Dup body",
            },
        )
        assert dup_resp.status_code == 400

        # Update & delete
        upd = await client.patch(
            f"/api/v1/macros/{created['id']}",
            headers=agent_headers,
            json={"title": "Reset VPN Updated"},
        )
        assert upd.status_code == 200
        assert upd.json()["title"] == "Reset VPN Updated"

        del_resp = await client.delete(
            f"/api/v1/macros/{created['id']}",
            headers=agent_headers,
        )
        assert del_resp.status_code == 204
