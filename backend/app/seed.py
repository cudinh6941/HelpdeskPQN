from datetime import datetime, timedelta, timezone
import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.models import (
    BusinessCalendar,
    Category,
    Department,
    SlaPolicy,
    SupportGroup,
    SupportGroupMember,
    Ticket,
    TicketComment,
    TicketPriority,
    TicketStatus,
    User,
    UserRole,
)
from app.services.outbox_writer import emit_outbox_event
from app.services.sla_engine import calculate_due_date

logger = logging.getLogger(__name__)

DEFAULT_KB_BY_SLUG: dict[str, list[dict]] = {
    "network-wifi-vpn": [
        {
            "id": "kb-vpn-credential",
            "title": "Khắc phục lỗi FortiClient VPN báo Credential failed",
            "keywords": ["vpn", "forticlient", "credential", "từ xa", "remote", "kết nối"],
            "steps": [
                "Kiểm tra lại mật khẩu đăng nhập máy tính Windows (nếu mới đổi mật khẩu AD, dùng mật khẩu mới nhất).",
                "Ngắt kết nối VPN hiện tại, chuyển sang mạng Wifi/4G khác nếu mạng nhà đang chặn port.",
                "Mở FortiClient -> chọn Settings -> kiểm tra đúng cổng SSL VPN và thử đăng nhập lại với tên user ngắn (không kèm @domain).",
            ],
        },
        {
            "id": "kb-lan-wifi",
            "title": "Xử lý máy tính mất mạng LAN / Wifi báo chấm than vàng",
            "keywords": ["mạng", "wifi", "lan", "internet", "chậm", "ip", "chấm than"],
            "steps": [
                "Rút và cắm lại dây mạng LAN ở mặt sau PC hoặc bật/tắt lại công tắc Wifi trên laptop.",
                "Mở Start -> gõ cmd -> chạy lệnh ipconfig /release rồi ipconfig /renew để cấp lại IP nội bộ.",
                "Nếu vẫn mất mạng, chụp ảnh đèn cổng LAN hoặc gửi mã ổ mạng để IT kiểm tra port switch.",
            ],
        },
    ],
    "printer-scanner": [
        {
            "id": "kb-printer-jam",
            "title": "Cách lấy giấy kẹt & khởi động lại lệnh in máy in Canon tầng 2",
            "keywords": ["máy in", "in", "kẹt giấy", "canon", "scan", "lệnh in", "mực"],
            "steps": [
                "Tắt công tắc nguồn máy in ở bên hông trước khi mở nắp khay giấy.",
                "Kéo nhẹ tờ giấy bị kẹt theo đúng chiều giấy ra (tránh giật mạnh làm rách giấy kẹt trong cụm sấy).",
                "Bật lại máy in; trên máy tính mở Control Panel -> Devices and Printers -> Cancel các lệnh in cũ bị treo rồi in thử lại.",
            ],
        },
    ],
    "erp-accounting": [
        {
            "id": "kb-misa-token",
            "title": "Sửa lỗi phần mềm MISA không nhận chữ ký số USB Token",
            "keywords": ["misa", "erp", "hóa đơn", "token", "chữ ký số", "xml", "kế toán"],
            "steps": [
                "Rút USB Token và cắm trực tiếp vào cổng USB phía sau thùng máy PC (không cắm qua hub chia USB).",
                "Kiểm tra ở khay đồng hồ góc dưới bên phải màn hình xem phần mềm quản lý Token (VD: VNPT-CA / Viettel-CA) đã chạy chưa.",
                "Khởi động lại dịch vụ MISA KySo / Plugin ký số và mở lại phần mềm MISA để xuất lại hóa đơn.",
            ],
        },
    ],
    "account-email-ad": [
        {
            "id": "kb-ad-lockout",
            "title": "Hướng dẫn xử lý khi tài khoản AD / Email bị khóa tạm thời",
            "keywords": ["mật khẩu", "password", "khóa", "ad", "tài khoản", "email", "outlook"],
            "steps": [
                "Kiểm tra phím CapsLock hoặc bộ gõ tiếng Việt (EVKey/Unikey) đang bật chế độ Tiếng Việt khi gõ mật khẩu.",
                "Nếu vừa đổi mật khẩu trên máy tính, nhớ cập nhật lại mật khẩu mới trên Outlook điện thoại để tránh tự động khóa tài khoản AD.",
                "Gửi ticket kèm tên đăng nhập để IT mở khóa tức thì và hỗ trợ reset nếu quên mật khẩu.",
            ],
        },
    ],
    "pc-laptop-hardware": [
        {
            "id": "kb-pc-freeze",
            "title": "Xử lý nhanh máy tính bị treo ứng dụng hoặc màn hình đen sau khi Sleep",
            "keywords": ["treo", "đơ", "chậm", "màn hình", "laptop", "pc", "sleep", "không lên"],
            "steps": [
                "Nhấn tổ hợp phím Ctrl + Shift + Windows + B để khởi động lại driver màn hình tức thì (không làm mất file đang mở).",
                "Nhấn Ctrl + Shift + Esc mở Task Manager -> chọn ứng dụng đang Not Responding -> bấm End Task.",
                "Nếu máy vẫn treo cứng, giữ nút nguồn 10 giây để tắt hẳn rồi bật lại và gửi ticket nếu lỗi lặp lại.",
            ],
        },
    ],
    "request-other": [
        {
            "id": "kb-software-install",
            "title": "Quy trình cài đặt phần mềm mới & cấp thiết bị ngoại vi",
            "keywords": ["cài đặt", "phần mềm", "teams", "chuột", "tai nghe", "cấp phát"],
            "steps": [
                "Ghi rõ tên phần mềm cần cài hoặc thiết bị cần cấp phát ngay trong tiêu đề ticket.",
                "Đính kèm UltraViewer ID & Pass ở form bên cạnh để IT kết nối cài đặt từ xa không cần chờ.",
                "Với phần mềm có bản quyền trả phí, vui lòng đính kèm ảnh chụp xác nhận từ Trưởng bộ phận.",
            ],
        },
    ],
}


async def ensure_kb_articles_seeded(db: AsyncSession) -> None:
    """Populate default self-help KB articles in Category.form_schema if empty."""
    cats = list((await db.execute(select(Category))).scalars().all())
    changed = False
    for cat in cats:
        existing_schema = dict(cat.form_schema or {})
        if not existing_schema.get("kb_articles") and cat.slug in DEFAULT_KB_BY_SLUG:
            existing_schema["kb_articles"] = DEFAULT_KB_BY_SLUG[cat.slug]
            cat.form_schema = existing_schema
            changed = True
    if changed:
        await db.commit()


async def seed_initial_data(db: AsyncSession) -> None:
    existing_users = (await db.execute(select(func.count(User.id)))).scalar_one()
    if existing_users > 0:
        await ensure_kb_articles_seeded(db)
        return

    logger.info("Seeding initial IT Helpdesk master data & sample tickets...")
    now = datetime.now(timezone.utc)

    # 1. Departments
    dept_kt = Department(code="KT", name="Phòng Kế toán", description="Tài chính & Kế toán")
    dept_kd = Department(code="KD", name="Phòng Kinh doanh", description="Kinh doanh & Chăm sóc khách hàng")
    dept_ns = Department(code="NS", name="Phòng Nhân sự", description="Hành chính & Nhân sự")
    dept_it = Department(code="IT", name="Phòng CNTT", description="Phòng Công nghệ thông tin")
    db.add_all([dept_kt, dept_kd, dept_ns, dept_it])
    await db.flush()

    # 2. Support Groups
    grp_l1 = SupportGroup(code="L1_HELPDESK", name="Helpdesk L1", description="Tiếp nhận & xử lý sự cố phổ thông")
    grp_net = SupportGroup(code="NET_INFRA", name="Hạ tầng & Mạng", description="Wifi, VPN, Firewall, Switch")
    grp_erp = SupportGroup(code="ERP_APP", name="Phần mềm & ERP", description="Phần mềm kế toán, ERP, Email")
    grp_hw = SupportGroup(code="HARDWARE", name="Phần cứng & Thiết bị", description="Laptop, PC, Máy in, Scan")
    db.add_all([grp_l1, grp_net, grp_erp, grp_hw])
    await db.flush()

    # 3. SLA Policies
    sla_low = SlaPolicy(
        name="SLA Thấp (LOW)",
        priority=TicketPriority.LOW,
        first_response_minutes=120,
        resolution_minutes=1440,
        warning_threshold_pct=80,
        business_hours_only=True,
    )
    sla_med = SlaPolicy(
        name="SLA Trung bình (MEDIUM)",
        priority=TicketPriority.MEDIUM,
        first_response_minutes=30,
        resolution_minutes=480,
        warning_threshold_pct=80,
        business_hours_only=True,
    )
    sla_high = SlaPolicy(
        name="SLA Cao (HIGH)",
        priority=TicketPriority.HIGH,
        first_response_minutes=15,
        resolution_minutes=240,
        warning_threshold_pct=75,
        business_hours_only=True,
    )
    sla_crit = SlaPolicy(
        name="SLA Khẩn cấp (CRITICAL)",
        priority=TicketPriority.CRITICAL,
        first_response_minutes=5,
        resolution_minutes=60,
        warning_threshold_pct=70,
        business_hours_only=False,
    )
    db.add_all([sla_low, sla_med, sla_high, sla_crit])
    await db.flush()

    # 4. Default Business Calendar
    calendar = BusinessCalendar(
        name="Giờ hành chính chuẩn (08:00 - 17:30)",
        timezone="Asia/Ho_Chi_Minh",
        work_days={
            "0": ["08:00", "17:30"],
            "1": ["08:00", "17:30"],
            "2": ["08:00", "17:30"],
            "3": ["08:00", "17:30"],
            "4": ["08:00", "17:30"],
        },
        holidays=["2026-01-01", "2026-04-30", "2026-05-01", "2026-09-02"],
        is_default=True,
    )
    db.add(calendar)
    await db.flush()

    # 5. Categories
    cat_net = Category(
        name="Mạng / Wifi / VPN",
        slug="network-wifi-vpn",
        description="Mất kết nối Internet, lỗi VPN công ty, Wifi chập chờn",
        default_group_id=grp_net.id,
        default_priority=TicketPriority.HIGH,
        sort_order=1,
    )
    cat_pc = Category(
        name="Máy tính / Laptop / Màn hình",
        slug="pc-laptop-hardware",
        description="Máy chậm, màn hình xanh, không lên nguồn, hỏng bàn phím/chuột",
        default_group_id=grp_hw.id,
        default_priority=TicketPriority.MEDIUM,
        sort_order=2,
    )
    cat_prn = Category(
        name="Máy in / Máy scan",
        slug="printer-scanner",
        description="Kẹt giấy, không nhận lệnh in, hết mực, lỗi scan",
        default_group_id=grp_hw.id,
        default_priority=TicketPriority.LOW,
        sort_order=3,
    )
    cat_acc = Category(
        name="Tài khoản / Email / AD",
        slug="account-email-ad",
        description="Quên mật khẩu, khóa tài khoản AD, cấp quyền thư mục chia sẻ",
        default_group_id=grp_l1.id,
        default_priority=TicketPriority.HIGH,
        sort_order=4,
    )
    cat_erp = Category(
        name="Phần mềm ERP / Kế toán",
        slug="erp-accounting",
        description="Lỗi phần mềm MISA/ERP, hóa đơn điện tử, chữ ký số",
        default_group_id=grp_erp.id,
        default_priority=TicketPriority.HIGH,
        sort_order=5,
    )
    cat_req = Category(
        name="Yêu cầu cấp phát / Khác",
        slug="request-other",
        description="Cài đặt phần mềm mới, cấp chuột/tai nghe, yêu cầu khác",
        default_group_id=grp_l1.id,
        default_priority=TicketPriority.LOW,
        sort_order=6,
    )
    db.add_all([cat_net, cat_pc, cat_prn, cat_acc, cat_erp, cat_req])
    await db.flush()

    # 6. Users (4 RBAC roles, default local fallback password: Password123!)
    default_pw = hash_password("Password123!")
    u_user = User(
        username="nhanvien",
        email="an.nguyen@company.local",
        full_name="Nguyễn Văn An",
        password_hash=default_pw,
        role=UserRole.END_USER,
        department_id=dept_kt.id,
        ldap_dn="CN=Nguyen Van An,OU=KeToan,DC=company,DC=local",
    )
    u_user2 = User(
        username="nhanvien2",
        email="binh.tran@company.local",
        full_name="Trần Thị Bình",
        password_hash=default_pw,
        role=UserRole.END_USER,
        department_id=dept_kd.id,
        ldap_dn="CN=Tran Thi Binh,OU=KinhDoanh,DC=company,DC=local",
    )
    u_user3 = User(
        username="nhanvien3",
        email="cuong.le@company.local",
        full_name="Lê Minh Cường",
        password_hash=default_pw,
        role=UserRole.END_USER,
        department_id=dept_ns.id,
        ldap_dn="CN=Le Minh Cuong,OU=NhanSu,DC=company,DC=local",
    )
    u_user4 = User(
        username="nhanvien4",
        email="dung.pham@company.local",
        full_name="Phạm Thùy Dung",
        password_hash=default_pw,
        role=UserRole.END_USER,
        department_id=dept_kt.id,
        ldap_dn="CN=Pham Thuy Dung,OU=KeToan,DC=company,DC=local",
    )
    u_agent = User(
        username="kythuat",
        email="duc.tran@company.local",
        full_name="Trần Minh Đức",
        password_hash=default_pw,
        role=UserRole.IT_AGENT,
        department_id=dept_it.id,
        ldap_dn="CN=Tran Minh Duc,OU=IT,DC=company,DC=local",
    )
    u_lead = User(
        username="truongnhom",
        email="nam.le@company.local",
        full_name="Lê Hoàng Nam",
        password_hash=default_pw,
        role=UserRole.IT_LEAD,
        department_id=dept_it.id,
        ldap_dn="CN=Le Hoang Nam,OU=IT,DC=company,DC=local",
    )
    u_admin = User(
        username="admin",
        email="admin.it@company.local",
        full_name="Phạm Quản Trị",
        password_hash=default_pw,
        role=UserRole.SYS_ADMIN,
        department_id=dept_it.id,
        ldap_dn="CN=Pham Quan Tri,OU=IT,DC=company,DC=local",
    )
    db.add_all([u_user, u_user2, u_user3, u_user4, u_agent, u_lead, u_admin])
    await db.flush()

    # 7. Support Group Members
    db.add_all(
        [
            SupportGroupMember(group_id=grp_l1.id, user_id=u_agent.id, is_lead=False),
            SupportGroupMember(group_id=grp_hw.id, user_id=u_agent.id, is_lead=False),
            SupportGroupMember(group_id=grp_l1.id, user_id=u_lead.id, is_lead=True),
            SupportGroupMember(group_id=grp_net.id, user_id=u_lead.id, is_lead=True),
            SupportGroupMember(group_id=grp_erp.id, user_id=u_lead.id, is_lead=True),
        ]
    )

    # 8. Sample Tickets across lifecycle states
    t1_created = now - timedelta(minutes=25)
    t1 = Ticket(
        ticket_code="HD-2026-0001",
        title="Không kết nối được VPN khi làm việc từ xa",
        description="Sáng nay mình bật FortiClient VPN báo lỗi Credential failed dù vừa đăng nhập máy tính bình thường.",
        status=TicketStatus.NEW,
        priority=TicketPriority.HIGH,
        requester_id=u_user.id,
        support_group_id=grp_net.id,
        category_id=cat_net.id,
        sla_policy_id=sla_high.id,
        asset_code="LAP-KT-018",
        first_response_due_at=calculate_due_date(t1_created, 15, calendar, True),
        resolution_due_at=calculate_due_date(t1_created, 240, calendar, True),
        created_at=t1_created,
        updated_at=t1_created,
    )

    t2_created = now - timedelta(hours=2)
    t2 = Ticket(
        ticket_code="HD-2026-0002",
        title="Máy in tầng 2 báo kẹt giấy liên tục",
        description="Máy in Canon ở hành lang tầng 2 in hóa đơn bị kẹt giấy ở khay 1, đèn đỏ nhấp nháy.",
        status=TicketStatus.IN_PROGRESS,
        priority=TicketPriority.MEDIUM,
        requester_id=u_user.id,
        assignee_id=u_agent.id,
        support_group_id=grp_hw.id,
        category_id=cat_prn.id,
        sla_policy_id=sla_med.id,
        asset_code="PRN-T2-001",
        first_response_due_at=calculate_due_date(t2_created, 30, calendar, True),
        first_responded_at=t2_created + timedelta(minutes=8),
        resolution_due_at=calculate_due_date(t2_created, 480, calendar, True),
        created_at=t2_created,
        updated_at=now - timedelta(minutes=30),
    )

    t3_created = now - timedelta(hours=3)
    t3 = Ticket(
        ticket_code="HD-2026-0003",
        title="Phần mềm kế toán MISA không xuất được hóa đơn XML",
        description="Khi bấm ký số xuất hóa đơn điện tử hệ thống báo thiếu USB Token hoặc chưa cài plugin.",
        status=TicketStatus.WAITING_FOR_USER,
        priority=TicketPriority.HIGH,
        requester_id=u_user.id,
        assignee_id=u_agent.id,
        support_group_id=grp_erp.id,
        category_id=cat_erp.id,
        sla_policy_id=sla_high.id,
        asset_code="PC-KT-012",
        first_response_due_at=calculate_due_date(t3_created, 15, calendar, True),
        first_responded_at=t3_created + timedelta(minutes=10),
        resolution_due_at=calculate_due_date(t3_created, 240, calendar, True),
        sla_paused_at=now - timedelta(minutes=45),
        created_at=t3_created,
        updated_at=now - timedelta(minutes=45),
    )

    t4_created = now - timedelta(days=1, hours=2)
    t4 = Ticket(
        ticket_code="HD-2026-0004",
        title="Cài đặt Microsoft Teams và bộ gõ tiếng Việt",
        description="Nhờ IT cài giúp Teams bản mới nhất cho máy nhân viên mới nhận việc.",
        status=TicketStatus.RESOLVED,
        priority=TicketPriority.LOW,
        requester_id=u_user.id,
        assignee_id=u_agent.id,
        support_group_id=grp_l1.id,
        category_id=cat_req.id,
        sla_policy_id=sla_low.id,
        asset_code="LAP-KD-088",
        first_response_due_at=calculate_due_date(t4_created, 120, calendar, True),
        first_responded_at=t4_created + timedelta(minutes=15),
        resolution_due_at=calculate_due_date(t4_created, 1440, calendar, True),
        resolved_at=now - timedelta(days=1),
        created_at=t4_created,
        updated_at=now - timedelta(days=1),
    )

    db.add_all([t1, t2, t3, t4])
    await db.flush()

    db.add_all(
        [
            TicketComment(
                ticket_id=t2.id,
                author_id=u_agent.id,
                body="Mình đã tiếp nhận và đang lên kiểm tra cụm sấy + khay giấy máy in tầng 2.",
                is_internal=False,
                created_at=t2_created + timedelta(minutes=10),
                updated_at=t2_created + timedelta(minutes=10),
            ),
            TicketComment(
                ticket_id=t2.id,
                author_id=u_agent.id,
                body="Ghi chú nội bộ: Rulo kéo giấy hơi mòn, cần đề xuất thay vào cuối tuần.",
                is_internal=True,
                created_at=t2_created + timedelta(minutes=25),
                updated_at=t2_created + timedelta(minutes=25),
            ),
            TicketComment(
                ticket_id=t3.id,
                author_id=u_agent.id,
                body="Bạn kiểm tra giúp mình xem đã cắm lại USB Token vào cổng USB phía sau cây PC chưa nhé, hoặc gửi giúp mã TeamViewer/Ultraview.",
                is_internal=False,
                created_at=now - timedelta(minutes=45),
                updated_at=now - timedelta(minutes=45),
            ),
            TicketComment(
                ticket_id=t4.id,
                author_id=u_agent.id,
                body="Đã cài xong Microsoft Teams và EVKey, bạn đăng nhập lại kiểm tra giúp mình nhé.",
                is_internal=False,
                created_at=now - timedelta(days=1),
                updated_at=now - timedelta(days=1),
            ),
        ]
    )

    emit_outbox_event(
        db=db,
        ticket=t1,
        actor=u_user,
        event_type="TICKET_CREATED",
        summary=f"{u_user.full_name} đã tạo ticket {t1.ticket_code}",
        details={"priority": t1.priority.value, "asset_code": t1.asset_code},
    )
    emit_outbox_event(
        db=db,
        ticket=t2,
        actor=u_agent,
        event_type="TICKET_CLAIMED",
        summary=f"{u_agent.full_name} đã nhận xử lý ticket",
    )
    emit_outbox_event(
        db=db,
        ticket=t3,
        actor=u_agent,
        event_type="STATUS_CHANGED",
        summary="Trạng thái chuyển từ IN_PROGRESS sang WAITING_FOR_USER (Tạm dừng SLA)",
    )
    emit_outbox_event(
        db=db,
        ticket=t4,
        actor=u_agent,
        event_type="STATUS_CHANGED",
        summary="Trạng thái chuyển từ IN_PROGRESS sang RESOLVED",
    )

    await db.commit()
    await ensure_kb_articles_seeded(db)
    logger.info("Initial seed data committed successfully.")
