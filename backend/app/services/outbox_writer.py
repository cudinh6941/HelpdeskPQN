from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import OutboxEvent, OutboxStatus, Ticket, User


def emit_outbox_event(
    db: AsyncSession,
    ticket: Ticket,
    actor: Optional[User],
    event_type: str,
    summary: str,
    details: Optional[dict[str, Any]] = None,
    is_internal: bool = False,
) -> OutboxEvent:
    """
    Write an OutboxEvent row inside the current DB transaction.
    Internal IT notes are marked with is_internal=True in payload and do not trigger
    end-user external notifications (or can be filtered by n8n).
    """
    now = datetime.now(timezone.utc)
    payload = {
        "event_type": event_type,
        "occurred_at": now.isoformat(),
        "is_internal": is_internal,
        "summary": summary,
        "ticket": {
            "id": str(ticket.id),
            "ticket_code": ticket.ticket_code,
            "title": ticket.title,
            "status": ticket.status.value,
            "priority": ticket.priority.value,
            "asset_code": ticket.asset_code,
            "requester_id": str(ticket.requester_id),
            "assignee_id": str(ticket.assignee_id) if ticket.assignee_id else None,
            "support_group_id": str(ticket.support_group_id) if ticket.support_group_id else None,
            "resolution_due_at": ticket.resolution_due_at.isoformat() if ticket.resolution_due_at else None,
        },
        "actor": (
            {
                "id": str(actor.id),
                "username": actor.username,
                "full_name": actor.full_name,
                "role": actor.role.value,
            }
            if actor
            else None
        ),
        "details": details or {},
    }

    event = OutboxEvent(
        aggregate_type="TICKET",
        aggregate_id=ticket.id,
        actor_id=actor.id if actor else None,
        event_type=event_type,
        payload=payload,
        status=OutboxStatus.SENT if is_internal else OutboxStatus.PENDING,
        processed_at=now if is_internal else None,
        created_at=now,
    )
    db.add(event)
    return event
