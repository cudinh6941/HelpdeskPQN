from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status

from app.models.models import Ticket, TicketStatus, User, UserRole
from app.services.sla_engine import ensure_utc, pause_ticket_sla, resume_ticket_sla

IT_ROLES = {UserRole.IT_AGENT, UserRole.IT_LEAD, UserRole.SYS_ADMIN}

ALLOWED_TRANSITIONS: dict[TicketStatus, set[TicketStatus]] = {
    TicketStatus.NEW: {TicketStatus.ASSIGNED, TicketStatus.IN_PROGRESS, TicketStatus.CANCELLED},
    TicketStatus.ASSIGNED: {
        TicketStatus.IN_PROGRESS,
        TicketStatus.WAITING_FOR_USER,
        TicketStatus.CANCELLED,
    },
    TicketStatus.IN_PROGRESS: {
        TicketStatus.WAITING_FOR_USER,
        TicketStatus.RESOLVED,
        TicketStatus.ASSIGNED,
    },
    TicketStatus.WAITING_FOR_USER: {
        TicketStatus.IN_PROGRESS,
        TicketStatus.RESOLVED,
        TicketStatus.CLOSED,
    },
    TicketStatus.RESOLVED: {TicketStatus.CLOSED, TicketStatus.REOPENED},
    TicketStatus.REOPENED: {
        TicketStatus.IN_PROGRESS,
        TicketStatus.WAITING_FOR_USER,
        TicketStatus.RESOLVED,
    },
    TicketStatus.CLOSED: set(),
    TicketStatus.CANCELLED: set(),
}


def stamp_first_response_if_needed(ticket: Ticket, actor: User, now: datetime) -> None:
    if actor.role in IT_ROLES and ticket.first_responded_at is None:
        ticket.first_responded_at = now
        if ticket.first_response_due_at is not None:
            due = ensure_utc(ticket.first_response_due_at)
            if now > due:
                ticket.is_response_breached = True


def transition_ticket_status(
    ticket: Ticket,
    target_status: TicketStatus,
    actor: User,
    now: Optional[datetime] = None,
) -> tuple[TicketStatus, int]:
    """
    Validate and apply a ticket status transition according to RBAC and State Machine rules.
    Returns (previous_status, resumed_paused_seconds).
    """
    current = ensure_utc(now) or datetime.now(timezone.utc)
    previous_status = ticket.status

    if previous_status == target_status:
        return previous_status, 0

    allowed_targets = ALLOWED_TRANSITIONS.get(previous_status, set())
    if target_status not in allowed_targets:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Không thể chuyển trạng thái từ {previous_status.value} sang {target_status.value}.",
        )

    # RBAC check
    if actor.role == UserRole.END_USER:
        if ticket.requester_id != actor.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bạn chỉ có thể thao tác trên ticket của chính mình.",
            )
        end_user_allowed = {
            (TicketStatus.NEW, TicketStatus.CANCELLED),
            (TicketStatus.RESOLVED, TicketStatus.CLOSED),
            (TicketStatus.RESOLVED, TicketStatus.REOPENED),
            (TicketStatus.WAITING_FOR_USER, TicketStatus.IN_PROGRESS),
        }
        if (previous_status, target_status) not in end_user_allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Nhân viên không có quyền chuyển sang trạng thái này.",
            )

    resumed_seconds = 0
    if previous_status == TicketStatus.WAITING_FOR_USER and target_status != TicketStatus.WAITING_FOR_USER:
        resumed_seconds = resume_ticket_sla(ticket, current)

    if target_status == TicketStatus.WAITING_FOR_USER:
        pause_ticket_sla(ticket, current)

    if target_status == TicketStatus.RESOLVED:
        ticket.resolved_at = current
        if ticket.resolution_due_at is not None:
            due = ensure_utc(ticket.resolution_due_at)
            if current > due:
                ticket.is_resolution_breached = True

    if target_status == TicketStatus.CLOSED:
        ticket.closed_at = current
        if ticket.resolved_at is None:
            ticket.resolved_at = current

    if target_status == TicketStatus.REOPENED:
        ticket.resolved_at = None
        ticket.closed_at = None

    stamp_first_response_if_needed(ticket, actor, current)
    ticket.status = target_status
    ticket.updated_at = current

    return previous_status, resumed_seconds
