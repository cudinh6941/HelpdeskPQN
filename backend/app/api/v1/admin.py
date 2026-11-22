from datetime import date, datetime, timezone
from typing import Optional
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import hash_password, normalize_username, require_roles
from app.core.uuid_utils import uuid7
from app.models.models import (
    BusinessCalendar,
    Category,
    Department,
    OutboxEvent,
    OutboxStatus,
    SlaPolicy,
    SupportGroup,
    SupportGroupMember,
    User,
    UserRole,
)
from app.schemas.schemas import (
    AdminUserCreate,
    AutomationSettingsOut,
    AutomationSettingsUpdate,
    BusinessCalendarOut,
    BusinessCalendarUpdate,
    CategoryCreate,
    CategoryOut,
    CategoryUpdate,
    DepartmentCreate,
    DepartmentOut,
    DepartmentUpdate,
    KbArticleCreate,
    OutboxEventOut,
    SlaPolicyOut,
    SlaPolicyUpdate,
    SupportGroupCreate,
    SupportGroupDetailOut,
    SupportGroupMemberAdd,
    SupportGroupUpdate,
    UserOut,
    UserRoleUpdate,
)
from app.services.settings_service import get_automation_settings, update_automation_settings
from app.services.ticket_state_machine import IT_ROLES
from app.workers.sla_scanner import auto_close_stale_resolved_tickets

router = APIRouter(prefix="/admin", tags=["Administration & Outbox"])

LEAD_OR_ADMIN = require_roles(UserRole.IT_LEAD, UserRole.SYS_ADMIN)
ADMIN_ONLY = require_roles(UserRole.SYS_ADMIN)


def _validate_hhmm(value: str) -> tuple[int, int]:
    parts = value.strip().split(":")
    if len(parts) != 2 or not (parts[0].isdigit() and parts[1].isdigit()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Giờ làm việc không hợp lệ: '{value}' (cần định dạng HH:MM).",
        )
    hh, mm = int(parts[0]), int(parts[1])
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Giờ làm việc không hợp lệ: '{value}'.",
        )
    return hh, mm


async def _load_group_detail(db: AsyncSession, group_id: uuid.UUID) -> SupportGroupDetailOut:
    res = await db.execute(
        select(SupportGroup)
        .options(selectinload(SupportGroup.members).selectinload(SupportGroupMember.user))
        .where(SupportGroup.id == group_id)
    )
    group = res.scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy nhóm.")
    return SupportGroupDetailOut.model_validate(group)


@router.get("/categories", response_model=list[CategoryOut])
async def admin_list_categories(
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(Category).order_by(Category.sort_order, Category.name))
    return list(res.scalars().all())


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
async def admin_create_category(
    payload: CategoryCreate,
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    exists = (await db.execute(select(Category).where(Category.slug == payload.slug))).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slug danh mục đã tồn tại.")

    cat = Category(**payload.model_dump())
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return cat


@router.patch("/categories/{category_id}", response_model=CategoryOut)
async def admin_update_category(
    category_id: uuid.UUID,
    payload: CategoryUpdate,
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    cat = (await db.execute(select(Category).where(Category.id == category_id))).scalar_one_or_none()
    if cat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy danh mục.")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(cat, k, v)
    await db.commit()
    await db.refresh(cat)
    return cat


@router.get("/support-groups", response_model=list[SupportGroupDetailOut])
async def admin_list_groups(
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(SupportGroup)
        .options(selectinload(SupportGroup.members).selectinload(SupportGroupMember.user))
        .order_by(SupportGroup.name)
    )
    return [SupportGroupDetailOut.model_validate(g) for g in res.scalars().all()]


@router.post("/support-groups", response_model=SupportGroupDetailOut, status_code=status.HTTP_201_CREATED)
async def admin_create_group(
    payload: SupportGroupCreate,
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    code = payload.code.strip().upper()
    exists = (
        await db.execute(select(SupportGroup).where(SupportGroup.code == code))
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mã nhóm đã tồn tại.")
    group = SupportGroup(
        code=code,
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
    )
    db.add(group)
    await db.commit()
    return await _load_group_detail(db, group.id)


@router.patch("/support-groups/{group_id}", response_model=SupportGroupDetailOut)
async def admin_update_group(
    group_id: uuid.UUID,
    payload: SupportGroupUpdate,
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    group = (await db.execute(select(SupportGroup).where(SupportGroup.id == group_id))).scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy nhóm.")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(group, k, v)
    await db.commit()
    return await _load_group_detail(db, group.id)


@router.post("/support-groups/{group_id}/members", response_model=SupportGroupDetailOut)
async def admin_add_group_member(
    group_id: uuid.UUID,
    payload: SupportGroupMemberAdd,
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    group = (await db.execute(select(SupportGroup).where(SupportGroup.id == group_id))).scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy nhóm hỗ trợ.")

    target_user = (await db.execute(select(User).where(User.id == payload.user_id))).scalar_one_or_none()
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy nhân sự.")
    if not target_user.is_active or target_user.role not in IT_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chỉ có thể thêm nhân sự IT đang hoạt động vào nhóm hỗ trợ.",
        )

    existing = (
        await db.execute(
            select(SupportGroupMember).where(
                SupportGroupMember.group_id == group_id,
                SupportGroupMember.user_id == payload.user_id,
            )
        )
    ).scalar_one_or_none()

    if existing is None:
        db.add(
            SupportGroupMember(
                group_id=group_id,
                user_id=payload.user_id,
                is_lead=payload.is_lead,
            )
        )
    else:
        existing.is_lead = payload.is_lead

    await db.commit()
    return await _load_group_detail(db, group_id)


@router.delete("/support-groups/{group_id}/members/{user_id}", response_model=SupportGroupDetailOut)
async def admin_remove_group_member(
    group_id: uuid.UUID,
    user_id: uuid.UUID,
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    group = (await db.execute(select(SupportGroup).where(SupportGroup.id == group_id))).scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy nhóm hỗ trợ.")

    membership = (
        await db.execute(
            select(SupportGroupMember).where(
                SupportGroupMember.group_id == group_id,
                SupportGroupMember.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if membership is not None:
        await db.delete(membership)
        await db.commit()

    return await _load_group_detail(db, group_id)


@router.get("/sla-policies", response_model=list[SlaPolicyOut])
async def admin_list_sla_policies(
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(SlaPolicy).order_by(SlaPolicy.resolution_minutes))
    return list(res.scalars().all())


@router.patch("/sla-policies/{policy_id}", response_model=SlaPolicyOut)
async def admin_update_sla_policy(
    policy_id: uuid.UUID,
    payload: SlaPolicyUpdate,
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    policy = (await db.execute(select(SlaPolicy).where(SlaPolicy.id == policy_id))).scalar_one_or_none()
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy SLA policy.")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(policy, k, v)
    await db.commit()
    await db.refresh(policy)
    return policy


@router.get("/business-calendar", response_model=BusinessCalendarOut)
async def admin_get_business_calendar(
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    cal = (
        await db.execute(select(BusinessCalendar).where(BusinessCalendar.is_default == True))
    ).scalar_one_or_none()
    if cal is None:
        cal = BusinessCalendar(
            name="Giờ hành chính chuẩn (08:00 - 17:30)",
            timezone="Asia/Ho_Chi_Minh",
            work_days={
                "0": ["08:00", "17:30"],
                "1": ["08:00", "17:30"],
                "2": ["08:00", "17:30"],
                "3": ["08:00", "17:30"],
                "4": ["08:00", "17:30"],
            },
            holidays=[],
            is_default=True,
        )
        db.add(cal)
        await db.commit()
        await db.refresh(cal)
    return BusinessCalendarOut.model_validate(cal)


@router.patch("/business-calendar", response_model=BusinessCalendarOut)
async def admin_update_business_calendar(
    payload: BusinessCalendarUpdate,
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    cal = (
        await db.execute(select(BusinessCalendar).where(BusinessCalendar.is_default == True))
    ).scalar_one_or_none()
    if cal is None:
        await admin_get_business_calendar(_, db)
        cal = (
            await db.execute(select(BusinessCalendar).where(BusinessCalendar.is_default == True))
        ).scalar_one()

    if payload.name is not None:
        cal.name = payload.name.strip()

    if payload.timezone is not None:
        tz_name = payload.timezone.strip()
        if tz_name not in ("Asia/Ho_Chi_Minh", "Asia/Saigon", "UTC"):
            try:
                ZoneInfo(tz_name)
            except ZoneInfoNotFoundError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Múi giờ không hợp lệ: '{tz_name}'.",
                )
        cal.timezone = tz_name

    if payload.work_days is not None:
        normalized_days: dict[str, list[str]] = {}
        valid_keys = {str(i) for i in range(7)}
        for day_key, window in payload.work_days.items():
            if day_key not in valid_keys:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Ngày trong tuần không hợp lệ: '{day_key}' (dùng '0' đến '6').",
                )
            if not isinstance(window, list) or len(window) != 2:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Khung giờ mỗi ngày cần đúng 2 mốc [bắt đầu, kết thúc].",
                )
            sh, sm = _validate_hhmm(window[0])
            eh, em = _validate_hhmm(window[1])
            if (sh, sm) >= (eh, em):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Giờ bắt đầu phải nhỏ hơn giờ kết thúc ({window[0]} - {window[1]}).",
                )
            normalized_days[day_key] = [f"{sh:02d}:{sm:02d}", f"{eh:02d}:{em:02d}"]
        cal.work_days = normalized_days

    if payload.holidays is not None:
        parsed_holidays: set[str] = set()
        for item in payload.holidays:
            raw = item.strip()
            if not raw:
                continue
            try:
                parsed_holidays.add(date.fromisoformat(raw).isoformat())
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Ngày nghỉ lễ không đúng định dạng YYYY-MM-DD: '{raw}'.",
                )
        cal.holidays = sorted(parsed_holidays)

    await db.commit()
    await db.refresh(cal)
    return BusinessCalendarOut.model_validate(cal)


@router.get("/departments", response_model=list[DepartmentOut])
async def admin_list_departments(
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(Department).order_by(Department.name))
    return [DepartmentOut.model_validate(d) for d in res.scalars().all()]


@router.post("/departments", response_model=DepartmentOut, status_code=status.HTTP_201_CREATED)
async def admin_create_department(
    payload: DepartmentCreate,
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    code = payload.code.strip().upper()
    exists = (await db.execute(select(Department).where(Department.code == code))).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mã phòng ban đã tồn tại.")
    dept = Department(
        code=code,
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
    )
    db.add(dept)
    await db.commit()
    await db.refresh(dept)
    return DepartmentOut.model_validate(dept)


@router.patch("/departments/{dept_id}", response_model=DepartmentOut)
async def admin_update_department(
    dept_id: uuid.UUID,
    payload: DepartmentUpdate,
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    dept = (await db.execute(select(Department).where(Department.id == dept_id))).scalar_one_or_none()
    if dept is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy phòng ban.")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(dept, k, v.strip() if isinstance(v, str) else v)
    await db.commit()
    await db.refresh(dept)
    return DepartmentOut.model_validate(dept)


@router.get("/users", response_model=list[UserOut])
async def admin_list_users(
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(User).options(selectinload(User.department)).order_by(User.full_name)
    )
    return [UserOut.model_validate(u) for u in res.scalars().all()]


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def admin_create_user(
    payload: AdminUserCreate,
    _: User = Depends(ADMIN_ONLY),
    db: AsyncSession = Depends(get_db),
):
    username = normalize_username(payload.username)
    email = payload.email.strip().lower()
    if len(username) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tên đăng nhập không hợp lệ.")

    dup = (
        await db.execute(select(User).where(or_(User.username == username, User.email == email)))
    ).scalar_one_or_none()
    if dup is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username hoặc email đã tồn tại trong hệ thống.",
        )

    if payload.department_id is not None:
        dept = (
            await db.execute(select(Department).where(Department.id == payload.department_id))
        ).scalar_one_or_none()
        if dept is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy phòng ban.")

    new_user = User(
        username=username,
        email=email,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        role=payload.role,
        department_id=payload.department_id,
        telegram_chat_id=payload.telegram_chat_id.strip() or None if payload.telegram_chat_id else None,
        zalo_user_id=payload.zalo_user_id.strip() or None if payload.zalo_user_id else None,
        is_active=True,
    )
    db.add(new_user)
    await db.commit()

    res = await db.execute(
        select(User).options(selectinload(User.department)).where(User.id == new_user.id)
    )
    return UserOut.model_validate(res.scalar_one())


@router.patch("/users/{user_id}", response_model=UserOut)
async def admin_update_user(
    user_id: uuid.UUID,
    payload: UserRoleUpdate,
    _: User = Depends(ADMIN_ONLY),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(User).options(selectinload(User.department)).where(User.id == user_id)
    )
    user = res.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy người dùng.")

    updates = payload.model_dump(exclude_unset=True)
    if "department_id" in updates and updates["department_id"] is not None:
        dept = (
            await db.execute(select(Department).where(Department.id == updates["department_id"]))
        ).scalar_one_or_none()
        if dept is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy phòng ban.")

    for k, v in updates.items():
        if k in ("telegram_chat_id", "zalo_user_id"):
            v = v.strip() or None if isinstance(v, str) else None
        elif k == "full_name" and isinstance(v, str):
            v = v.strip()
        setattr(user, k, v)

    await db.commit()
    reloaded = (
        await db.execute(select(User).options(selectinload(User.department)).where(User.id == user_id))
    ).scalar_one()
    return UserOut.model_validate(reloaded)


@router.get("/outbox-events", response_model=list[OutboxEventOut])
async def admin_list_outbox_events(
    status_filter: Optional[OutboxStatus] = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(OutboxEvent).order_by(desc(OutboxEvent.created_at)).limit(limit)
    if status_filter is not None:
        stmt = stmt.where(OutboxEvent.status == status_filter)
    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.post("/outbox-events/{event_id}/retry", response_model=OutboxEventOut)
async def admin_retry_outbox_event(
    event_id: uuid.UUID,
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    ev = (await db.execute(select(OutboxEvent).where(OutboxEvent.id == event_id))).scalar_one_or_none()
    if ev is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy outbox event.")

    ev.status = OutboxStatus.PENDING
    ev.next_retry_at = datetime.now(timezone.utc)
    ev.last_error = None
    await db.commit()
    await db.refresh(ev)
    return ev


@router.post("/categories/{category_id}/kb", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
async def admin_add_kb_article(
    category_id: uuid.UUID,
    payload: KbArticleCreate,
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    cat = (await db.execute(select(Category).where(Category.id == category_id))).scalar_one_or_none()
    if cat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy danh mục.")

    schema = dict(cat.form_schema or {})
    articles = list(schema.get("kb_articles") or [])
    new_article = {
        "id": f"kb-{str(uuid7())[:8]}",
        "title": payload.title.strip(),
        "keywords": [k.strip().lower() for k in payload.keywords if k.strip()],
        "steps": [s.strip() for s in payload.steps if s.strip()],
    }
    articles.append(new_article)
    cat.form_schema = {**schema, "kb_articles": articles}
    await db.commit()
    await db.refresh(cat)
    return cat


@router.delete("/categories/{category_id}/kb/{article_id}", response_model=CategoryOut)
async def admin_delete_kb_article(
    category_id: uuid.UUID,
    article_id: str,
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    cat = (await db.execute(select(Category).where(Category.id == category_id))).scalar_one_or_none()
    if cat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy danh mục.")

    schema = dict(cat.form_schema or {})
    articles = [a for a in (schema.get("kb_articles") or []) if a.get("id") != article_id]
    cat.form_schema = {**schema, "kb_articles": articles}
    await db.commit()
    await db.refresh(cat)
    return cat


@router.get("/automation-settings", response_model=AutomationSettingsOut)
async def admin_get_automation_settings(
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    cfg = await get_automation_settings(db)
    return AutomationSettingsOut(**cfg)


@router.patch("/automation-settings", response_model=AutomationSettingsOut)
async def admin_update_automation_settings(
    payload: AutomationSettingsUpdate,
    current_user: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    cfg = await update_automation_settings(
        db,
        auto_assign_enabled=payload.auto_assign_enabled,
        auto_close_resolved_hours=payload.auto_close_resolved_hours,
        actor_id=current_user.id,
    )
    return AutomationSettingsOut(**cfg)


@router.post("/automation/run-auto-close")
async def admin_run_auto_close_now(
    hours: Optional[int] = Query(default=None, ge=1, le=720),
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    count = await auto_close_stale_resolved_tickets(db, max_age_hours=hours)
    return {"auto_closed": count}
