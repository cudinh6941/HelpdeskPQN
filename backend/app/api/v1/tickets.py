from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.attachments import serialize_attachment
from app.api.v1.kb import serialize_kb_brief
from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.core.ws_manager import ws_manager
from app.models.models import (
    BusinessCalendar,
    Category,
    KbArticle,
    OutboxEvent,
    SlaPolicy,
    SupportGroup,
    Ticket,
    TicketAttachment,
    TicketComment,
    TicketPriority,
    TicketStatus,
    User,
    UserRole,
)
from app.schemas.schemas import (
    CommentOut,
    SlaStatusOut,
    TicketAssignRequest,
    TicketBriefOut,
    TicketBulkActionRequest,
    TicketBulkActionResponse,
    TicketCreate,
    TicketDetailOut,
    TicketLinkParentRequest,
    TicketListResponse,
    TicketMergeRequest,
    TicketMetadataResponse,
    TicketOut,
    TicketPriorityUpdate,
    TicketRateRequest,
    TicketRelatedResponse,
    TicketStatusUpdate,
    TicketUpdateRequest,
    TimelineEventOut,
    UltraViewProvideRequest,
)
from app.services.auto_assign_service import pick_least_loaded_agent
from app.services.notification_service import create_ticket_notifications
from app.services.outbox_writer import emit_outbox_event
from app.services.settings_service import get_automation_settings
from app.services.sla_engine import calculate_due_date, ensure_utc, evaluate_ticket_sla, resume_ticket_sla
from app.services.ticket_code_generator import generate_ticket_code
from app.services.ticket_state_machine import IT_ROLES, stamp_first_response_if_needed, transition_ticket_status
from app.services.ultraview_service import extract_ultraview_credentials, normalize_uv_id

router = APIRouter(prefix="/tickets", tags=["Tickets"])


def _ticket_options():
    return [
        selectinload(Ticket.requester),
        selectinload(Ticket.assignee),
        selectinload(Ticket.support_group),
        selectinload(Ticket.category),
        selectinload(Ticket.sla_policy),
    ]


def _serialize_ticket(ticket: Ticket) -> TicketOut:
    data = TicketOut.model_validate(ticket)
    data.sla_status = SlaStatusOut(**evaluate_ticket_sla(ticket))
    return data


@router.get("/metadata", response_model=TicketMetadataResponse)
async def get_ticket_metadata(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cat_res = await db.execute(
        select(Category).where(Category.is_active == True).order_by(Category.sort_order, Category.name)
    )
    grp_res = await db.execute(
        select(SupportGroup).where(SupportGroup.is_active == True).order_by(SupportGroup.name)
    )
    sla_res = await db.execute(
        select(SlaPolicy).where(SlaPolicy.is_active == True).order_by(SlaPolicy.resolution_minutes)
    )
    agents: list[User] = []
    requesters: list[User] = []
    if current_user.role in IT_ROLES:
        agent_res = await db.execute(
            select(User)
            .where(User.is_active == True, User.role.in_(list(IT_ROLES)))
            .order_by(User.full_name)
        )
        agents = list(agent_res.scalars().all())
        req_res = await db.execute(
            select(User).where(User.is_active == True).order_by(User.full_name)
        )
        requesters = list(req_res.scalars().all())

    return TicketMetadataResponse(
        categories=list(cat_res.scalars().all()),
        support_groups=list(grp_res.scalars().all()),
        sla_policies=list(sla_res.scalars().all()),
        it_agents=agents,
        requesters=requesters,
    )


@router.get("", response_model=TicketListResponse)
async def list_tickets(
    status_filter: Optional[TicketStatus] = Query(default=None, alias="status"),
    priority: Optional[TicketPriority] = Query(default=None),
    category_id: Optional[uuid.UUID] = Query(default=None),
    support_group_id: Optional[uuid.UUID] = Query(default=None),
    assignee_id: Optional[uuid.UUID] = Query(default=None),
    asset_code: Optional[str] = Query(default=None),
    sla_breached: Optional[bool] = Query(default=None),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    mine: bool = Query(default=False),
    requested_by_me: bool = Query(default=False),
    unassigned_only: bool = Query(default=False),
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    filters = []

    if current_user.role == UserRole.END_USER or requested_by_me:
        filters.append(Ticket.requester_id == current_user.id)
    elif mine:
        filters.append(Ticket.assignee_id == current_user.id)

    if status_filter is not None:
        filters.append(Ticket.status == status_filter)
    if priority is not None:
        filters.append(Ticket.priority == priority)
    if category_id is not None:
        filters.append(Ticket.category_id == category_id)
    if support_group_id is not None:
        filters.append(Ticket.support_group_id == support_group_id)
    if assignee_id is not None:
        filters.append(Ticket.assignee_id == assignee_id)
    if unassigned_only:
        filters.append(Ticket.assignee_id.is_(None))
    if asset_code:
        filters.append(Ticket.asset_code.ilike(f"%{asset_code.strip()}%"))
    if sla_breached is not None:
        filters.append(Ticket.is_resolution_breached == sla_breached)
    if date_from is not None:
        filters.append(Ticket.created_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to is not None:
        filters.append(Ticket.created_at <= datetime.combine(date_to, time.max, tzinfo=timezone.utc))
    if q:
        term = f"%{q.strip()}%"
        filters.append(
            or_(
                Ticket.ticket_code.ilike(term),
                Ticket.title.ilike(term),
                Ticket.description.ilike(term),
                Ticket.asset_code.ilike(term),
            )
        )

    count_stmt = select(func.count(Ticket.id)).where(*filters)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(Ticket)
        .options(*_ticket_options())
        .where(*filters)
        .order_by(desc(Ticket.created_at))
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(stmt)).scalars().all()

    return TicketListResponse(items=[_serialize_ticket(t) for t in rows], total=total)


@router.post("", response_model=TicketDetailOut, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    payload: TicketCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    requester = current_user
    if payload.requester_id is not None and payload.requester_id != current_user.id:
        if current_user.role not in IT_ROLES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Chỉ nhân viên IT mới có quyền tạo ticket hộ người khác.",
            )
        req_user = (
            await db.execute(select(User).where(User.id == payload.requester_id))
        ).scalar_one_or_none()
        if req_user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy người yêu cầu.")
        if not req_user.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tài khoản người yêu cầu đã bị khóa.")
        requester = req_user

    category: Optional[Category] = None
    if payload.category_id is not None:
        cat_res = await db.execute(select(Category).where(Category.id == payload.category_id))
        category = cat_res.scalar_one_or_none()
        if category is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Danh mục sự cố không tồn tại.")

    priority = payload.priority or (category.default_priority if category else TicketPriority.MEDIUM)
    support_group_id = category.default_group_id if category else None

    sla_res = await db.execute(
        select(SlaPolicy).where(SlaPolicy.priority == priority, SlaPolicy.is_active == True)
    )
    sla_policy = sla_res.scalar_one_or_none()

    cal_res = await db.execute(select(BusinessCalendar).where(BusinessCalendar.is_default == True))
    calendar = cal_res.scalar_one_or_none()

    first_response_due_at = None
    resolution_due_at = None
    if sla_policy is not None:
        first_response_due_at = calculate_due_date(
            now, sla_policy.first_response_minutes, calendar, sla_policy.business_hours_only
        )
        resolution_due_at = calculate_due_date(
            now, sla_policy.resolution_minutes, calendar, sla_policy.business_hours_only
        )

    ticket_code = await generate_ticket_code(db)
    custom_data = dict(payload.custom_data or {})
    uv_id_raw = (payload.ultraview_id or "").strip()
    uv_pass_raw = (payload.ultraview_pass or "").strip()
    if uv_id_raw and uv_pass_raw:
        custom_data["ultraview"] = {
            "id": normalize_uv_id(uv_id_raw) or uv_id_raw,
            "pass": uv_pass_raw,
            "state": "READY",
            "updated_at": now.isoformat(),
        }
    else:
        detected_uv = extract_ultraview_credentials(payload.description)
        if detected_uv:
            custom_data["ultraview"] = {
                "id": detected_uv["id"],
                "pass": detected_uv["pass"],
                "state": "READY",
                "updated_at": now.isoformat(),
            }

    ticket = Ticket(
        ticket_code=ticket_code,
        title=payload.title.strip(),
        description=payload.description.strip(),
        status=TicketStatus.NEW,
        priority=priority,
        requester_id=requester.id,
        support_group_id=support_group_id,
        category_id=category.id if category else None,
        sla_policy_id=sla_policy.id if sla_policy else None,
        asset_code=payload.asset_code.strip().upper() if payload.asset_code else None,
        custom_data=custom_data,
        first_response_due_at=first_response_due_at,
        resolution_due_at=resolution_due_at,
        created_at=now,
        updated_at=now,
    )

    auto_assigned_agent: Optional[User] = None
    if payload.assign_to_me and current_user.role in IT_ROLES:
        ticket.assignee_id = current_user.id
        ticket.status = TicketStatus.IN_PROGRESS
        ticket.first_responded_at = now
    else:
        auto_cfg = await get_automation_settings(db)
        if auto_cfg["auto_assign_enabled"]:
            auto_assigned_agent = await pick_least_loaded_agent(db, support_group_id)
            if auto_assigned_agent is not None:
                ticket.assignee_id = auto_assigned_agent.id
                ticket.status = TicketStatus.ASSIGNED

    db.add(ticket)
    await db.flush()

    if payload.attachment_ids:
        att_res = await db.execute(
            select(TicketAttachment).where(TicketAttachment.id.in_(payload.attachment_ids))
        )
        for att in att_res.scalars().all():
            if att.uploader_id == current_user.id or current_user.role in IT_ROLES:
                att.ticket_id = ticket.id

    on_behalf = requester.id != current_user.id
    outbox_details = {
        "category": category.name if category else None,
        "priority": priority.value,
        "asset_code": ticket.asset_code,
    }
    if on_behalf:
        outbox_details["on_behalf_of"] = requester.full_name

    emit_outbox_event(
        db=db,
        ticket=ticket,
        actor=current_user,
        event_type="TICKET_CREATED",
        summary=(
            f"{current_user.full_name} tạo ticket {ticket.ticket_code} hộ {requester.full_name}"
            if on_behalf
            else f"{current_user.full_name} đã tạo ticket {ticket.ticket_code}"
        ),
        details=outbox_details,
    )

    if auto_assigned_agent is not None:
        emit_outbox_event(
            db=db,
            ticket=ticket,
            actor=None,
            event_type="TICKET_AUTO_ASSIGNED",
            summary=f"Tự động phân công cho {auto_assigned_agent.full_name} (Least-loaded)",
            details={"assignee_id": str(auto_assigned_agent.id)},
        )

    await create_ticket_notifications(
        db=db,
        ticket=ticket,
        event_type="TICKET_CREATED",
        title=f"Ticket mới: {ticket.ticket_code}",
        body=(
            f"{current_user.full_name} tạo ticket hộ {requester.full_name}: {ticket.title}"
            if on_behalf
            else f"{current_user.full_name} tạo ticket (tự động giao cho {auto_assigned_agent.full_name}): {ticket.title}"
            if auto_assigned_agent
            else f"{current_user.full_name} vừa tạo ticket mới: {ticket.title}"
        ),
        actor_id=current_user.id,
    )

    await db.commit()
    await ws_manager.broadcast_ticket_event(
        "TICKET_CREATED",
        str(ticket.id),
        str(ticket.requester_id),
        payload={
            "ticket_code": ticket.ticket_code,
            "title": ticket.title,
            "priority": ticket.priority.value,
            "actor_id": str(current_user.id),
            "actor_name": current_user.full_name,
            "summary": (
                f"{current_user.full_name} tạo {ticket.ticket_code} (giao cho {auto_assigned_agent.full_name})"
                if auto_assigned_agent
                else f"{current_user.full_name} vừa tạo {ticket.ticket_code}: {ticket.title}"
            ),
        },
    )
    return await get_ticket_detail(ticket.id, current_user, db)


@router.post("/bulk", response_model=TicketBulkActionResponse)
async def bulk_ticket_action(
    payload: TicketBulkActionRequest,
    current_user: User = Depends(require_roles(UserRole.IT_AGENT, UserRole.IT_LEAD, UserRole.SYS_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    unique_ids = list(dict.fromkeys(payload.ticket_ids))
    target_assignee: Optional[User] = None
    target_group: Optional[SupportGroup] = None
    sla_policy: Optional[SlaPolicy] = None
    calendar: Optional[BusinessCalendar] = None

    if payload.action == "assign":
        if payload.assignee_id is None and payload.support_group_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cần chọn kỹ thuật viên hoặc nhóm hỗ trợ để phân công.",
            )
        if payload.assignee_id is not None:
            target_assignee = (
                await db.execute(select(User).where(User.id == payload.assignee_id))
            ).scalar_one_or_none()
            if target_assignee is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy kỹ thuật viên.")
        if payload.support_group_id is not None:
            target_group = (
                await db.execute(select(SupportGroup).where(SupportGroup.id == payload.support_group_id))
            ).scalar_one_or_none()
            if target_group is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy nhóm kỹ thuật.")
    elif payload.action == "status":
        if payload.status is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Thiếu trạng thái đích.")
    elif payload.action == "priority":
        if payload.priority is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Thiếu độ ưu tiên đích.")
        sla_policy = (
            await db.execute(
                select(SlaPolicy).where(SlaPolicy.priority == payload.priority, SlaPolicy.is_active == True)
            )
        ).scalar_one_or_none()
        calendar = (
            await db.execute(select(BusinessCalendar).where(BusinessCalendar.is_default == True))
        ).scalar_one_or_none()

    rows = (await db.execute(select(Ticket).where(Ticket.id.in_(unique_ids)))).scalars().all()
    ticket_map = {t.id: t for t in rows}

    now = datetime.now(timezone.utc)
    updated = 0
    skipped = 0
    errors: list[str] = []
    ws_events: list[tuple[str, str, str, dict]] = []

    for tid in unique_ids:
        ticket = ticket_map.get(tid)
        if ticket is None:
            skipped += 1
            errors.append(f"Không tìm thấy ticket {tid}")
            continue

        if payload.action == "claim":
            ticket.assignee_id = current_user.id
            if ticket.status in (TicketStatus.NEW, TicketStatus.ASSIGNED, TicketStatus.REOPENED):
                transition_ticket_status(ticket, TicketStatus.IN_PROGRESS, current_user, now)
            else:
                stamp_first_response_if_needed(ticket, current_user, now)
                ticket.updated_at = now
            ev_type = "TICKET_CLAIMED"
            summary = f"{current_user.full_name} đã nhận xử lý ticket"
            details = {"assignee_id": str(current_user.id), "bulk": True}
        elif payload.action == "assign":
            if target_assignee is not None:
                ticket.assignee_id = target_assignee.id
            if target_group is not None:
                ticket.support_group_id = target_group.id
            if ticket.status == TicketStatus.NEW and target_assignee is not None:
                transition_ticket_status(ticket, TicketStatus.ASSIGNED, current_user, now)
            else:
                stamp_first_response_if_needed(ticket, current_user, now)
                ticket.updated_at = now
            ev_type = "TICKET_ASSIGNED"
            summary = (
                f"{current_user.full_name} phân công cho {target_assignee.full_name}"
                if target_assignee
                else f"{current_user.full_name} chuyển nhóm sang {target_group.name if target_group else ''}"
            )
            details = {
                "assignee_id": str(ticket.assignee_id) if ticket.assignee_id else None,
                "support_group_id": str(ticket.support_group_id) if ticket.support_group_id else None,
                "bulk": True,
            }
        elif payload.action == "status":
            try:
                prev_status, resumed_seconds = transition_ticket_status(
                    ticket, payload.status, current_user, now
                )
            except HTTPException as exc:
                skipped += 1
                errors.append(f"{ticket.ticket_code}: {exc.detail}")
                continue
            ev_type = "STATUS_CHANGED"
            summary = f"Trạng thái chuyển từ {prev_status.value} sang {ticket.status.value}"
            details = {
                "from_status": prev_status.value,
                "to_status": ticket.status.value,
                "resumed_sla_seconds": resumed_seconds,
                "bulk": True,
            }
        else:  # priority
            if ticket.status in (TicketStatus.CLOSED, TicketStatus.CANCELLED):
                skipped += 1
                errors.append(f"{ticket.ticket_code}: Không thể đổi ưu tiên ticket đã đóng/hủy.")
                continue
            prev_priority = ticket.priority
            if prev_priority == payload.priority:
                skipped += 1
                continue
            ticket.priority = payload.priority
            ticket.updated_at = now
            if sla_policy is not None:
                ticket.sla_policy_id = sla_policy.id
                created_utc = ensure_utc(ticket.created_at) or now
                if ticket.first_responded_at is None:
                    ticket.first_response_due_at = calculate_due_date(
                        created_utc, sla_policy.first_response_minutes, calendar, sla_policy.business_hours_only
                    )
                base_res_due = calculate_due_date(
                    created_utc, sla_policy.resolution_minutes, calendar, sla_policy.business_hours_only
                )
                paused_sec = int(ticket.total_paused_seconds or 0)
                ticket.resolution_due_at = (
                    base_res_due + timedelta(seconds=paused_sec) if paused_sec > 0 else base_res_due
                )
            ev_type = "PRIORITY_CHANGED"
            summary = f"Độ ưu tiên đổi từ {prev_priority.value} sang {ticket.priority.value}"
            details = {"from_priority": prev_priority.value, "to_priority": ticket.priority.value, "bulk": True}

        emit_outbox_event(
            db=db,
            ticket=ticket,
            actor=current_user,
            event_type=ev_type,
            summary=summary,
            details=details,
        )
        await create_ticket_notifications(
            db=db,
            ticket=ticket,
            event_type=ev_type,
            title=f"Cập nhật {ticket.ticket_code}",
            body=summary,
            actor_id=current_user.id,
        )
        ws_events.append(
            (
                str(ticket.id),
                str(ticket.requester_id),
                {
                    "ticket_code": ticket.ticket_code,
                    "title": ticket.title,
                    "priority": ticket.priority.value,
                    "actor_id": str(current_user.id),
                    "actor_name": current_user.full_name,
                    "summary": f"{ticket.ticket_code}: {summary}",
                },
            )
        )
        updated += 1

    if updated > 0:
        await db.commit()
        for t_id_str, req_id_str, ws_payload in ws_events:
            await ws_manager.broadcast_ticket_event(
                "TICKET_UPDATED",
                t_id_str,
                req_id_str,
                payload=ws_payload,
            )

    return TicketBulkActionResponse(updated=updated, skipped=skipped, errors=errors)


@router.get("/{ticket_id}", response_model=TicketDetailOut)
async def get_ticket_detail(
    ticket_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Ticket)
        .options(
            *_ticket_options(),
            selectinload(Ticket.comments).selectinload(TicketComment.author),
            selectinload(Ticket.comments).selectinload(TicketComment.attachments),
            selectinload(Ticket.comments).selectinload(TicketComment.kb_article).selectinload(KbArticle.category),
            selectinload(Ticket.comments).selectinload(TicketComment.kb_article).selectinload(KbArticle.attachments),
            selectinload(Ticket.attachments),
        )
        .where(Ticket.id == ticket_id)
    )
    ticket = (await db.execute(stmt)).scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy ticket.")

    if current_user.role == UserRole.END_USER and ticket.requester_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bạn không có quyền xem ticket này.")

    ev_res = await db.execute(
        select(OutboxEvent)
        .where(OutboxEvent.aggregate_id == ticket.id)
        .order_by(OutboxEvent.created_at)
    )
    events = ev_res.scalars().all()

    is_it = current_user.role in IT_ROLES
    visible_comments = [
        CommentOut(
            id=c.id,
            ticket_id=c.ticket_id,
            author_id=c.author_id,
            author=c.author,
            body=c.body,
            is_internal=c.is_internal,
            kb_article_id=c.kb_article_id,
            kb_article=serialize_kb_brief(c.kb_article, include_notes=is_it) if c.kb_article else None,
            created_at=c.created_at,
            attachments=[serialize_attachment(a) for a in c.attachments],
        )
        for c in ticket.comments
        if is_it or not c.is_internal
    ]

    visible_timeline = [
        TimelineEventOut.model_validate(ev)
        for ev in events
        if is_it or not ev.payload.get("is_internal", False)
    ]

    top_attachments = [
        serialize_attachment(a) for a in ticket.attachments if a.comment_id is None
    ]

    base = _serialize_ticket(ticket)
    return TicketDetailOut(
        **base.model_dump(),
        comments=visible_comments,
        attachments=top_attachments,
        timeline=visible_timeline,
    )


@router.patch("/{ticket_id}", response_model=TicketDetailOut)
async def update_ticket_fields(
    ticket_id: uuid.UUID,
    payload: TicketUpdateRequest,
    current_user: User = Depends(require_roles(UserRole.IT_AGENT, UserRole.IT_LEAD, UserRole.SYS_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    ticket = (await db.execute(select(Ticket).where(Ticket.id == ticket_id))).scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy ticket.")

    fields = payload.model_fields_set
    changed_fields: list[str] = []

    if "title" in fields and payload.title is not None:
        ticket.title = payload.title.strip()
        changed_fields.append("title")

    if "category_id" in fields:
        if payload.category_id is not None:
            cat = (
                await db.execute(select(Category).where(Category.id == payload.category_id))
            ).scalar_one_or_none()
            if cat is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy danh mục.")
        ticket.category_id = payload.category_id
        changed_fields.append("category_id")

    if "asset_code" in fields:
        clean_asset = payload.asset_code.strip().upper() if payload.asset_code else None
        ticket.asset_code = clean_asset or None
        changed_fields.append("asset_code")

    if "support_group_id" in fields:
        if payload.support_group_id is not None:
            grp = (
                await db.execute(select(SupportGroup).where(SupportGroup.id == payload.support_group_id))
            ).scalar_one_or_none()
            if grp is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy nhóm kỹ thuật.")
        ticket.support_group_id = payload.support_group_id
        changed_fields.append("support_group_id")

    if changed_fields:
        ticket.updated_at = datetime.now(timezone.utc)
        emit_outbox_event(
            db=db,
            ticket=ticket,
            actor=current_user,
            event_type="TICKET_UPDATED",
            summary=f"{current_user.full_name} cập nhật thông tin ticket ({', '.join(changed_fields)})",
            details={"changed_fields": changed_fields, "asset_code": ticket.asset_code},
            is_internal=True,
        )
        await db.commit()
        await ws_manager.broadcast_ticket_event(
            "TICKET_UPDATED",
            str(ticket.id),
            str(ticket.requester_id),
            is_internal=True,
            payload={
                "ticket_code": ticket.ticket_code,
                "title": ticket.title,
                "priority": ticket.priority.value,
                "actor_id": str(current_user.id),
                "actor_name": current_user.full_name,
                "summary": f"{ticket.ticket_code} được cập nhật thuộc tính",
            },
        )

    return await get_ticket_detail(ticket.id, current_user, db)


@router.get("/{ticket_id}/related", response_model=TicketRelatedResponse)
async def get_ticket_related(
    ticket_id: uuid.UUID,
    _: User = Depends(require_roles(UserRole.IT_AGENT, UserRole.IT_LEAD, UserRole.SYS_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    ticket = (await db.execute(select(Ticket).where(Ticket.id == ticket_id))).scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy ticket.")

    by_asset: list[Ticket] = []
    if ticket.asset_code:
        asset_res = await db.execute(
            select(Ticket)
            .where(Ticket.asset_code == ticket.asset_code, Ticket.id != ticket.id)
            .order_by(desc(Ticket.created_at))
            .limit(5)
        )
        by_asset = list(asset_res.scalars().all())

    req_res = await db.execute(
        select(Ticket)
        .where(Ticket.requester_id == ticket.requester_id, Ticket.id != ticket.id)
        .order_by(desc(Ticket.created_at))
        .limit(5)
    )
    by_requester = list(req_res.scalars().all())

    parent_ticket: Optional[Ticket] = None
    if ticket.parent_ticket_id is not None:
        parent_ticket = (
            await db.execute(select(Ticket).where(Ticket.id == ticket.parent_ticket_id))
        ).scalar_one_or_none()

    children_res = await db.execute(
        select(Ticket)
        .where(Ticket.parent_ticket_id == ticket.id)
        .order_by(Ticket.created_at)
    )
    children = list(children_res.scalars().all())

    return TicketRelatedResponse(
        by_asset=[TicketBriefOut.model_validate(t) for t in by_asset],
        by_requester=[TicketBriefOut.model_validate(t) for t in by_requester],
        parent=TicketBriefOut.model_validate(parent_ticket) if parent_ticket else None,
        children=[TicketBriefOut.model_validate(t) for t in children],
    )


@router.post("/{ticket_id}/link-parent", response_model=TicketDetailOut)
async def link_parent_ticket(
    ticket_id: uuid.UUID,
    payload: TicketLinkParentRequest,
    current_user: User = Depends(require_roles(UserRole.IT_AGENT, UserRole.IT_LEAD, UserRole.SYS_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    ticket = (await db.execute(select(Ticket).where(Ticket.id == ticket_id))).scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy ticket.")

    parent_code: Optional[str] = None
    if payload.parent_ticket_id is None:
        ticket.parent_ticket_id = None
    else:
        if payload.parent_ticket_id == ticket.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Không thể liên kết ticket với chính nó.",
            )
        parent = (
            await db.execute(select(Ticket).where(Ticket.id == payload.parent_ticket_id))
        ).scalar_one_or_none()
        if parent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy ticket tổng.")
        if parent.parent_ticket_id is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ticket tổng đích đang là ticket con của một sự cố khác.",
            )
        has_children = (
            await db.execute(select(Ticket.id).where(Ticket.parent_ticket_id == ticket.id).limit(1))
        ).scalar_one_or_none()
        if has_children is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ticket này đang có ticket con nên không thể gắn làm ticket con.",
            )
        ticket.parent_ticket_id = parent.id
        parent_code = parent.ticket_code

    ticket.updated_at = datetime.now(timezone.utc)
    emit_outbox_event(
        db=db,
        ticket=ticket,
        actor=current_user,
        event_type="TICKET_LINKED",
        summary=(
            f"{current_user.full_name} liên kết ticket vào sự cố tổng {parent_code}"
            if parent_code
            else f"{current_user.full_name} gỡ liên kết sự cố tổng"
        ),
        details={"parent_ticket_id": str(ticket.parent_ticket_id) if ticket.parent_ticket_id else None},
        is_internal=True,
    )
    await db.commit()
    await ws_manager.broadcast_ticket_event(
        "TICKET_UPDATED",
        str(ticket.id),
        str(ticket.requester_id),
        is_internal=True,
        payload={
            "ticket_code": ticket.ticket_code,
            "title": ticket.title,
            "priority": ticket.priority.value,
            "actor_id": str(current_user.id),
            "actor_name": current_user.full_name,
            "summary": f"{ticket.ticket_code}: cập nhật liên kết sự cố",
        },
    )
    return await get_ticket_detail(ticket.id, current_user, db)


@router.post("/{ticket_id}/merge", response_model=TicketDetailOut)
async def merge_ticket(
    ticket_id: uuid.UUID,
    payload: TicketMergeRequest,
    current_user: User = Depends(require_roles(UserRole.IT_AGENT, UserRole.IT_LEAD, UserRole.SYS_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    if payload.target_ticket_id == ticket_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Không thể gộp ticket vào chính nó.",
        )

    source = (
        await db.execute(
            select(Ticket).options(selectinload(Ticket.requester)).where(Ticket.id == ticket_id)
        )
    ).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy ticket nguồn.")
    if source.status in (TicketStatus.CLOSED, TicketStatus.CANCELLED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ticket đã đóng hoặc đã hủy không thể gộp.",
        )

    target = (
        await db.execute(select(Ticket).where(Ticket.id == payload.target_ticket_id))
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy ticket đích.")
    if target.status in (TicketStatus.CLOSED, TicketStatus.CANCELLED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ticket đích đã đóng hoặc đã hủy.",
        )

    now = datetime.now(timezone.utc)
    stamp_first_response_if_needed(source, current_user, now)
    source.parent_ticket_id = target.id
    source.sla_paused_at = None
    source.status = TicketStatus.CLOSED
    source.resolved_at = source.resolved_at or now
    source.closed_at = now
    source.updated_at = now

    note_suffix = f" ({payload.note.strip()})" if payload.note and payload.note.strip() else ""
    db.add(
        TicketComment(
            ticket_id=source.id,
            author_id=current_user.id,
            body=f"Ticket này đã được gộp vào {target.ticket_code} ({target.title}){note_suffix}. Mọi cập nhật tiếp theo sẽ được xử lý ở ticket chính.",
            is_internal=False,
            created_at=now,
            updated_at=now,
        )
    )
    requester_name = source.requester.full_name if source.requester else "Nhân viên"
    db.add(
        TicketComment(
            ticket_id=target.id,
            author_id=current_user.id,
            body=f"Đã gộp ticket trùng {source.ticket_code} từ {requester_name}: {source.title}{note_suffix}",
            is_internal=True,
            created_at=now,
            updated_at=now,
        )
    )

    emit_outbox_event(
        db=db,
        ticket=source,
        actor=current_user,
        event_type="TICKET_MERGED",
        summary=f"{current_user.full_name} đã gộp {source.ticket_code} vào {target.ticket_code}",
        details={"target_ticket_id": str(target.id), "target_ticket_code": target.ticket_code},
    )
    emit_outbox_event(
        db=db,
        ticket=target,
        actor=current_user,
        event_type="TICKET_MERGED",
        summary=f"Đã gộp ticket {source.ticket_code} vào {target.ticket_code}",
        details={"source_ticket_id": str(source.id), "source_ticket_code": source.ticket_code},
        is_internal=True,
    )
    await create_ticket_notifications(
        db=db,
        ticket=source,
        event_type="TICKET_MERGED",
        title=f"{source.ticket_code} đã gộp vào {target.ticket_code}",
        body=f"{current_user.full_name} đã gộp {source.ticket_code} vào {target.ticket_code}.",
        actor_id=current_user.id,
    )
    await create_ticket_notifications(
        db=db,
        ticket=target,
        event_type="TICKET_MERGED",
        title=f"Gộp ticket vào {target.ticket_code}",
        body=f"{source.ticket_code} đã được gộp vào {target.ticket_code}.",
        actor_id=current_user.id,
        is_internal=True,
    )

    await db.commit()
    await ws_manager.broadcast_ticket_event(
        "TICKET_UPDATED",
        str(source.id),
        str(source.requester_id),
        payload={
            "ticket_code": source.ticket_code,
            "title": source.title,
            "priority": source.priority.value,
            "actor_id": str(current_user.id),
            "actor_name": current_user.full_name,
            "summary": f"{source.ticket_code} đã gộp vào {target.ticket_code}",
        },
    )
    await ws_manager.broadcast_ticket_event(
        "TICKET_UPDATED",
        str(target.id),
        str(target.requester_id),
        is_internal=True,
        payload={
            "ticket_code": target.ticket_code,
            "title": target.title,
            "priority": target.priority.value,
            "actor_id": str(current_user.id),
            "actor_name": current_user.full_name,
            "summary": f"Đã gộp {source.ticket_code} vào {target.ticket_code}",
        },
    )
    return await get_ticket_detail(source.id, current_user, db)


@router.post("/{ticket_id}/claim", response_model=TicketDetailOut)
async def claim_ticket(
    ticket_id: uuid.UUID,
    current_user: User = Depends(require_roles(UserRole.IT_AGENT, UserRole.IT_LEAD, UserRole.SYS_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = res.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy ticket.")

    now = datetime.now(timezone.utc)
    ticket.assignee_id = current_user.id
    if ticket.status in (TicketStatus.NEW, TicketStatus.ASSIGNED, TicketStatus.REOPENED):
        transition_ticket_status(ticket, TicketStatus.IN_PROGRESS, current_user, now)
    else:
        stamp_first_response_if_needed(ticket, current_user, now)
        ticket.updated_at = now

    emit_outbox_event(
        db=db,
        ticket=ticket,
        actor=current_user,
        event_type="TICKET_CLAIMED",
        summary=f"{current_user.full_name} đã nhận xử lý ticket",
        details={"assignee_id": str(current_user.id)},
    )
    await create_ticket_notifications(
        db=db,
        ticket=ticket,
        event_type="TICKET_CLAIMED",
        title=f"Đã tiếp nhận {ticket.ticket_code}",
        body=f"{current_user.full_name} đã nhận xử lý {ticket.ticket_code}.",
        actor_id=current_user.id,
    )
    await db.commit()
    await ws_manager.broadcast_ticket_event(
        "TICKET_UPDATED",
        str(ticket.id),
        str(ticket.requester_id),
        payload={
            "ticket_code": ticket.ticket_code,
            "title": ticket.title,
            "priority": ticket.priority.value,
            "actor_id": str(current_user.id),
            "actor_name": current_user.full_name,
            "summary": f"{current_user.full_name} đã nhận xử lý {ticket.ticket_code}",
        },
    )
    return await get_ticket_detail(ticket.id, current_user, db)


@router.post("/{ticket_id}/assign", response_model=TicketDetailOut)
async def assign_ticket(
    ticket_id: uuid.UUID,
    payload: TicketAssignRequest,
    current_user: User = Depends(require_roles(UserRole.IT_AGENT, UserRole.IT_LEAD, UserRole.SYS_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = res.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy ticket.")

    now = datetime.now(timezone.utc)
    assignee_name = None
    if payload.assignee_id is not None:
        u_res = await db.execute(select(User).where(User.id == payload.assignee_id))
        assignee = u_res.scalar_one_or_none()
        if assignee is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy kỹ thuật viên.")
        ticket.assignee_id = assignee.id
        assignee_name = assignee.full_name

    if payload.support_group_id is not None:
        g_res = await db.execute(select(SupportGroup).where(SupportGroup.id == payload.support_group_id))
        group = g_res.scalar_one_or_none()
        if group is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy nhóm kỹ thuật.")
        ticket.support_group_id = group.id

    if ticket.status == TicketStatus.NEW and payload.assignee_id is not None:
        transition_ticket_status(ticket, TicketStatus.ASSIGNED, current_user, now)
    else:
        stamp_first_response_if_needed(ticket, current_user, now)
        ticket.updated_at = now

    emit_outbox_event(
        db=db,
        ticket=ticket,
        actor=current_user,
        event_type="TICKET_ASSIGNED",
        summary=(
            f"{current_user.full_name} phân công cho {assignee_name}"
            if assignee_name
            else f"{current_user.full_name} cập nhật nhóm xử lý"
        ),
        details={
            "assignee_id": str(ticket.assignee_id) if ticket.assignee_id else None,
            "support_group_id": str(ticket.support_group_id) if ticket.support_group_id else None,
        },
    )
    await create_ticket_notifications(
        db=db,
        ticket=ticket,
        event_type="TICKET_ASSIGNED",
        title=f"Phân công {ticket.ticket_code}",
        body=(
            f"{current_user.full_name} phân công {ticket.ticket_code} cho {assignee_name}."
            if assignee_name
            else f"{current_user.full_name} cập nhật nhóm xử lý {ticket.ticket_code}."
        ),
        actor_id=current_user.id,
    )
    await db.commit()
    await ws_manager.broadcast_ticket_event(
        "TICKET_UPDATED",
        str(ticket.id),
        str(ticket.requester_id),
        payload={
            "ticket_code": ticket.ticket_code,
            "title": ticket.title,
            "priority": ticket.priority.value,
            "actor_id": str(current_user.id),
            "actor_name": current_user.full_name,
            "summary": f"{ticket.ticket_code}: cập nhật phân công xử lý",
        },
    )
    return await get_ticket_detail(ticket.id, current_user, db)


@router.patch("/{ticket_id}/status", response_model=TicketDetailOut)
async def update_ticket_status(
    ticket_id: uuid.UUID,
    payload: TicketStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = res.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy ticket.")

    now = datetime.now(timezone.utc)
    prev_status, resumed_seconds = transition_ticket_status(ticket, payload.status, current_user, now)

    if payload.note and payload.note.strip():
        db.add(
            TicketComment(
                ticket_id=ticket.id,
                author_id=current_user.id,
                body=payload.note.strip(),
                is_internal=False,
                created_at=now,
                updated_at=now,
            )
        )

    emit_outbox_event(
        db=db,
        ticket=ticket,
        actor=current_user,
        event_type="STATUS_CHANGED",
        summary=f"Trạng thái chuyển từ {prev_status.value} sang {ticket.status.value}",
        details={
            "from_status": prev_status.value,
            "to_status": ticket.status.value,
            "resumed_sla_seconds": resumed_seconds,
            "note": payload.note,
        },
    )
    await create_ticket_notifications(
        db=db,
        ticket=ticket,
        event_type="STATUS_CHANGED",
        title=f"{ticket.ticket_code}: {ticket.status.value}",
        body=f"{current_user.full_name} chuyển trạng thái từ {prev_status.value} sang {ticket.status.value}.",
        actor_id=current_user.id,
    )

    cascade_ws_events: list[tuple[str, str, dict]] = []
    if payload.status == TicketStatus.RESOLVED and payload.cascade_children:
        child_res = await db.execute(
            select(Ticket).where(
                Ticket.parent_ticket_id == ticket.id,
                Ticket.status.notin_(
                    [TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.CANCELLED]
                ),
            )
        )
        for child in child_res.scalars().all():
            child_prev = child.status
            if child.status == TicketStatus.WAITING_FOR_USER:
                resume_ticket_sla(child, now)
            stamp_first_response_if_needed(child, current_user, now)
            child.status = TicketStatus.RESOLVED
            child.resolved_at = now
            child.updated_at = now
            if child.resolution_due_at is not None and now > ensure_utc(child.resolution_due_at):
                child.is_resolution_breached = True

            cascade_msg = f"Sự cố tổng {ticket.ticket_code} đã được xử lý."
            if payload.note and payload.note.strip():
                cascade_msg = f"{cascade_msg} {payload.note.strip()}"
            db.add(
                TicketComment(
                    ticket_id=child.id,
                    author_id=current_user.id,
                    body=cascade_msg,
                    is_internal=False,
                    created_at=now,
                    updated_at=now,
                )
            )
            emit_outbox_event(
                db=db,
                ticket=child,
                actor=current_user,
                event_type="STATUS_CHANGED",
                summary=f"Tự động xử lý theo sự cố tổng {ticket.ticket_code} ({child_prev.value} -> RESOLVED)",
                details={
                    "from_status": child_prev.value,
                    "to_status": TicketStatus.RESOLVED.value,
                    "parent_ticket_code": ticket.ticket_code,
                },
            )
            await create_ticket_notifications(
                db=db,
                ticket=child,
                event_type="STATUS_CHANGED",
                title=f"{child.ticket_code}: RESOLVED",
                body=cascade_msg,
                actor_id=current_user.id,
            )
            cascade_ws_events.append(
                (
                    str(child.id),
                    str(child.requester_id),
                    {
                        "ticket_code": child.ticket_code,
                        "title": child.title,
                        "priority": child.priority.value,
                        "actor_id": str(current_user.id),
                        "actor_name": current_user.full_name,
                        "summary": f"{child.ticket_code} đã được xử lý theo {ticket.ticket_code}",
                    },
                )
            )

    await db.commit()
    await ws_manager.broadcast_ticket_event(
        "TICKET_UPDATED",
        str(ticket.id),
        str(ticket.requester_id),
        payload={
            "ticket_code": ticket.ticket_code,
            "title": ticket.title,
            "priority": ticket.priority.value,
            "actor_id": str(current_user.id),
            "actor_name": current_user.full_name,
            "summary": f"{ticket.ticket_code} chuyển sang {ticket.status.value}",
        },
    )
    for c_id, c_req, c_payload in cascade_ws_events:
        await ws_manager.broadcast_ticket_event(
            "TICKET_UPDATED",
            c_id,
            c_req,
            payload=c_payload,
        )
    return await get_ticket_detail(ticket.id, current_user, db)


@router.patch("/{ticket_id}/priority", response_model=TicketDetailOut)
async def update_ticket_priority(
    ticket_id: uuid.UUID,
    payload: TicketPriorityUpdate,
    current_user: User = Depends(require_roles(UserRole.IT_AGENT, UserRole.IT_LEAD, UserRole.SYS_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = res.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy ticket.")

    if ticket.status in (TicketStatus.CLOSED, TicketStatus.CANCELLED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Không thể đổi độ ưu tiên của ticket đã đóng hoặc đã hủy.",
        )

    prev_priority = ticket.priority
    if prev_priority == payload.priority:
        return await get_ticket_detail(ticket.id, current_user, db)

    now = datetime.now(timezone.utc)
    ticket.priority = payload.priority
    ticket.updated_at = now

    sla_res = await db.execute(
        select(SlaPolicy).where(SlaPolicy.priority == payload.priority, SlaPolicy.is_active == True)
    )
    sla_policy = sla_res.scalar_one_or_none()
    cal_res = await db.execute(select(BusinessCalendar).where(BusinessCalendar.is_default == True))
    calendar = cal_res.scalar_one_or_none()

    if sla_policy is not None:
        ticket.sla_policy_id = sla_policy.id
        created_utc = ensure_utc(ticket.created_at) or now
        if ticket.first_responded_at is None:
            ticket.first_response_due_at = calculate_due_date(
                created_utc, sla_policy.first_response_minutes, calendar, sla_policy.business_hours_only
            )
        base_resolution_due = calculate_due_date(
            created_utc, sla_policy.resolution_minutes, calendar, sla_policy.business_hours_only
        )
        paused_sec = int(ticket.total_paused_seconds or 0)
        ticket.resolution_due_at = (
            base_resolution_due + timedelta(seconds=paused_sec) if paused_sec > 0 else base_resolution_due
        )

    emit_outbox_event(
        db=db,
        ticket=ticket,
        actor=current_user,
        event_type="PRIORITY_CHANGED",
        summary=f"Độ ưu tiên đổi từ {prev_priority.value} sang {ticket.priority.value}",
        details={
            "from_priority": prev_priority.value,
            "to_priority": ticket.priority.value,
        },
    )
    await create_ticket_notifications(
        db=db,
        ticket=ticket,
        event_type="PRIORITY_CHANGED",
        title=f"Đổi ưu tiên {ticket.ticket_code}",
        body=f"{current_user.full_name} đổi độ ưu tiên từ {prev_priority.value} sang {ticket.priority.value}.",
        actor_id=current_user.id,
    )
    await db.commit()
    await ws_manager.broadcast_ticket_event(
        "TICKET_UPDATED",
        str(ticket.id),
        str(ticket.requester_id),
        payload={
            "ticket_code": ticket.ticket_code,
            "title": ticket.title,
            "priority": ticket.priority.value,
            "actor_id": str(current_user.id),
            "actor_name": current_user.full_name,
            "summary": f"{ticket.ticket_code} đổi ưu tiên sang {ticket.priority.value}",
        },
    )
    return await get_ticket_detail(ticket.id, current_user, db)


@router.post("/{ticket_id}/rate", response_model=TicketDetailOut)
async def rate_ticket(
    ticket_id: uuid.UUID,
    payload: TicketRateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = res.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy ticket.")

    if ticket.requester_id != current_user.id and current_user.role != UserRole.SYS_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Chỉ người tạo ticket mới được đánh giá.")

    if ticket.status not in (TicketStatus.RESOLVED, TicketStatus.CLOSED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chỉ có thể đánh giá sau khi ticket đã được xử lý (RESOLVED/CLOSED).",
        )

    now = datetime.now(timezone.utc)
    ticket.rating = payload.rating
    ticket.feedback = payload.feedback.strip() if payload.feedback else None
    if payload.close_ticket and ticket.status == TicketStatus.RESOLVED:
        transition_ticket_status(ticket, TicketStatus.CLOSED, current_user, now)
    else:
        ticket.updated_at = now

    emit_outbox_event(
        db=db,
        ticket=ticket,
        actor=current_user,
        event_type="TICKET_RATED",
        summary=f"{current_user.full_name} đánh giá {payload.rating}/5 sao",
        details={"rating": payload.rating, "feedback": ticket.feedback},
    )
    await create_ticket_notifications(
        db=db,
        ticket=ticket,
        event_type="TICKET_RATED",
        title=f"Đánh giá {ticket.ticket_code}: {payload.rating}/5 ★",
        body=f"{current_user.full_name} đã đánh giá {payload.rating}/5 sao cho {ticket.ticket_code}.",
        actor_id=current_user.id,
    )
    await db.commit()
    await ws_manager.broadcast_ticket_event("TICKET_UPDATED", str(ticket.id), str(ticket.requester_id))
    return await get_ticket_detail(ticket.id, current_user, db)


@router.post("/{ticket_id}/ultraview/request", response_model=TicketDetailOut)
async def request_ultraview(
    ticket_id: uuid.UUID,
    current_user: User = Depends(require_roles(UserRole.IT_AGENT, UserRole.IT_LEAD, UserRole.SYS_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = res.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy ticket.")

    now = datetime.now(timezone.utc)
    if ticket.assignee_id is None:
        ticket.assignee_id = current_user.id

    if ticket.status == TicketStatus.NEW:
        transition_ticket_status(ticket, TicketStatus.IN_PROGRESS, current_user, now)

    if ticket.status in (
        TicketStatus.ASSIGNED,
        TicketStatus.IN_PROGRESS,
        TicketStatus.REOPENED,
    ):
        transition_ticket_status(ticket, TicketStatus.WAITING_FOR_USER, current_user, now)
    else:
        stamp_first_response_if_needed(ticket, current_user, now)
        ticket.updated_at = now

    existing_uv = dict((ticket.custom_data or {}).get("ultraview") or {})
    existing_uv.update(
        {
            "state": "REQUESTED",
            "requested_by": current_user.full_name,
            "updated_at": now.isoformat(),
        }
    )
    ticket.custom_data = {**(ticket.custom_data or {}), "ultraview": existing_uv}

    db.add(
        TicketComment(
            ticket_id=ticket.id,
            author_id=current_user.id,
            body="Yêu cầu kết nối UltraViewer để kiểm tra và xử lý trực tiếp trên máy.",
            is_internal=False,
            created_at=now,
            updated_at=now,
        )
    )

    emit_outbox_event(
        db=db,
        ticket=ticket,
        actor=current_user,
        event_type="ULTRAVIEW_REQUESTED",
        summary=f"{current_user.full_name} đã yêu cầu kết nối UltraViewer",
        details={"requested_by": current_user.full_name},
    )
    await create_ticket_notifications(
        db=db,
        ticket=ticket,
        event_type="ULTRAVIEW_REQUESTED",
        title=f"Yêu cầu UltraViewer: {ticket.ticket_code}",
        body=f"{current_user.full_name} yêu cầu kết nối UltraViewer để hỗ trợ trực tiếp.",
        actor_id=current_user.id,
    )

    await db.commit()
    await ws_manager.broadcast_ticket_event(
        "ULTRAVIEW_REQUESTED",
        str(ticket.id),
        str(ticket.requester_id),
        payload={
            "ticket_code": ticket.ticket_code,
            "title": ticket.title,
            "priority": ticket.priority.value,
            "actor_id": str(current_user.id),
            "actor_name": current_user.full_name,
            "requested_by": current_user.full_name,
            "summary": f"{current_user.full_name} yêu cầu kết nối UltraViewer cho {ticket.ticket_code}",
        },
    )
    return await get_ticket_detail(ticket.id, current_user, db)


@router.post("/{ticket_id}/ultraview/provide", response_model=TicketDetailOut)
async def provide_ultraview(
    ticket_id: uuid.UUID,
    payload: UltraViewProvideRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = res.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy ticket.")

    if current_user.role == UserRole.END_USER and ticket.requester_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền gửi thông tin UltraViewer cho ticket này.",
        )

    now = datetime.now(timezone.utc)
    uv_id = normalize_uv_id(payload.ultraview_id) or payload.ultraview_id.strip()
    uv_pass = payload.ultraview_pass.strip()

    ticket.custom_data = {
        **(ticket.custom_data or {}),
        "ultraview": {
            "id": uv_id,
            "pass": uv_pass,
            "state": "READY",
            "updated_at": now.isoformat(),
        },
    }

    resumed_seconds = 0
    if ticket.status == TicketStatus.WAITING_FOR_USER:
        resumed_seconds = resume_ticket_sla(ticket, now)
        ticket.status = TicketStatus.IN_PROGRESS
        ticket.updated_at = now
    else:
        ticket.updated_at = now

    db.add(
        TicketComment(
            ticket_id=ticket.id,
            author_id=current_user.id,
            body=f"Thông tin kết nối UltraViewer — ID: {uv_id} / Pass: {uv_pass}",
            is_internal=False,
            created_at=now,
            updated_at=now,
        )
    )

    emit_outbox_event(
        db=db,
        ticket=ticket,
        actor=current_user,
        event_type="ULTRAVIEW_PROVIDED",
        summary=f"{current_user.full_name} đã gửi thông tin UltraViewer",
        details={"ultraview_id": uv_id, "resumed_sla_seconds": resumed_seconds},
    )
    await create_ticket_notifications(
        db=db,
        ticket=ticket,
        event_type="ULTRAVIEW_PROVIDED",
        title=f"Đã gửi UltraViewer: {ticket.ticket_code}",
        body=f"{current_user.full_name} đã gửi thông tin UltraViewer (ID: {uv_id}).",
        actor_id=current_user.id,
    )

    await db.commit()
    await ws_manager.broadcast_ticket_event(
        "ULTRAVIEW_PROVIDED",
        str(ticket.id),
        str(ticket.requester_id),
        payload={
            "ticket_code": ticket.ticket_code,
            "title": ticket.title,
            "priority": ticket.priority.value,
            "actor_id": str(current_user.id),
            "actor_name": current_user.full_name,
            "ultraview_id": uv_id,
            "summary": f"{current_user.full_name} đã gửi UltraViewer ID/Pass cho {ticket.ticket_code}",
        },
    )
    return await get_ticket_detail(ticket.id, current_user, db)
