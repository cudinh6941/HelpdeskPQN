from datetime import datetime, timezone
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.attachments import serialize_attachment
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.core.ws_manager import ws_manager
from app.models.models import (
    BusinessCalendar,
    Category,
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
    TicketCreate,
    TicketDetailOut,
    TicketListResponse,
    TicketMetadataResponse,
    TicketOut,
    TicketRateRequest,
    TicketStatusUpdate,
    TimelineEventOut,
    UltraViewProvideRequest,
)
from app.services.auto_assign_service import pick_least_loaded_agent
from app.services.outbox_writer import emit_outbox_event
from app.services.sla_engine import calculate_due_date, evaluate_ticket_sla, resume_ticket_sla
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
    if current_user.role in IT_ROLES:
        agent_res = await db.execute(
            select(User)
            .where(User.is_active == True, User.role.in_(list(IT_ROLES)))
            .order_by(User.full_name)
        )
        agents = list(agent_res.scalars().all())

    return TicketMetadataResponse(
        categories=list(cat_res.scalars().all()),
        support_groups=list(grp_res.scalars().all()),
        sla_policies=list(sla_res.scalars().all()),
        it_agents=agents,
    )


@router.get("", response_model=TicketListResponse)
async def list_tickets(
    status_filter: Optional[TicketStatus] = Query(default=None, alias="status"),
    priority: Optional[TicketPriority] = Query(default=None),
    support_group_id: Optional[uuid.UUID] = Query(default=None),
    assignee_id: Optional[uuid.UUID] = Query(default=None),
    asset_code: Optional[str] = Query(default=None),
    sla_breached: Optional[bool] = Query(default=None),
    mine: bool = Query(default=False),
    unassigned_only: bool = Query(default=False),
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    filters = []

    if current_user.role == UserRole.END_USER or mine:
        if current_user.role == UserRole.END_USER:
            filters.append(Ticket.requester_id == current_user.id)
        else:
            filters.append(Ticket.assignee_id == current_user.id)

    if status_filter is not None:
        filters.append(Ticket.status == status_filter)
    if priority is not None:
        filters.append(Ticket.priority == priority)
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
        requester_id=current_user.id,
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
    if get_settings().AUTO_ASSIGN_ENABLED:
        auto_assigned_agent = await pick_least_loaded_agent(db, support_group_id)
        if auto_assigned_agent is not None:
            ticket.assignee_id = auto_assigned_agent.id
            ticket.status = TicketStatus.ASSIGNED
            ticket.first_responded_at = now

    db.add(ticket)
    await db.flush()

    if payload.attachment_ids:
        att_res = await db.execute(
            select(TicketAttachment).where(TicketAttachment.id.in_(payload.attachment_ids))
        )
        for att in att_res.scalars().all():
            if att.uploader_id == current_user.id or current_user.role in IT_ROLES:
                att.ticket_id = ticket.id

    emit_outbox_event(
        db=db,
        ticket=ticket,
        actor=current_user,
        event_type="TICKET_CREATED",
        summary=f"{current_user.full_name} đã tạo ticket {ticket.ticket_code}",
        details={
            "category": category.name if category else None,
            "priority": priority.value,
            "asset_code": ticket.asset_code,
        },
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
