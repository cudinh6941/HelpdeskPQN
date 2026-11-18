from datetime import datetime, timedelta, timezone
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.ws_manager import ws_manager
from app.models.models import Ticket, TicketStatus
from app.services.outbox_writer import emit_outbox_event
from app.services.sla_engine import ensure_utc, evaluate_ticket_sla

logger = logging.getLogger(__name__)

TERMINAL_OR_PAUSED_STATUSES = {
    TicketStatus.RESOLVED,
    TicketStatus.CLOSED,
    TicketStatus.CANCELLED,
    TicketStatus.WAITING_FOR_USER,
}


async def auto_close_stale_resolved_tickets(
    db: AsyncSession,
    now: Optional[datetime] = None,
    max_age_hours: Optional[int] = None,
) -> int:
    """
    Close RESOLVED tickets whose resolved_at is older than AUTO_CLOSE_RESOLVED_HOURS.
    Returns the number of tickets closed.
    """
    settings = get_settings()
    hours_threshold = (
        max_age_hours if max_age_hours is not None else settings.AUTO_CLOSE_RESOLVED_HOURS
    )
    current = ensure_utc(now) or datetime.now(timezone.utc)
    cutoff = current - timedelta(hours=max(1, hours_threshold))

    stmt = select(Ticket).where(
        Ticket.status == TicketStatus.RESOLVED,
        Ticket.resolved_at.is_not(None),
    )
    if db.bind and db.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)

    resolved_tickets = list((await db.execute(stmt)).scalars().all())
    closed_tickets: list[Ticket] = []

    for t in resolved_tickets:
        resolved_utc = ensure_utc(t.resolved_at)
        if resolved_utc is not None and resolved_utc <= cutoff:
            t.status = TicketStatus.CLOSED
            t.closed_at = current
            t.updated_at = current
            closed_tickets.append(t)
            emit_outbox_event(
                db=db,
                ticket=t,
                actor=None,
                event_type="TICKET_AUTO_CLOSED",
                summary=f"Hệ thống tự động đóng ticket {t.ticket_code} sau {hours_threshold}h ở trạng thái RESOLVED",
                details={"auto_closed_hours": hours_threshold},
            )

    if closed_tickets:
        await db.commit()
        for t in closed_tickets:
            await ws_manager.broadcast_ticket_event(
                "TICKET_UPDATED",
                str(t.id),
                str(t.requester_id),
                payload={
                    "ticket_code": t.ticket_code,
                    "title": t.title,
                    "priority": t.priority.value,
                    "summary": f"Ticket {t.ticket_code} đã tự động đóng",
                },
            )
        logger.info("Auto-closed %d stale RESOLVED tickets.", len(closed_tickets))
    else:
        await db.rollback()

    return len(closed_tickets)


async def scan_sla_deadlines(db: AsyncSession, now: Optional[datetime] = None) -> dict[str, int]:
    """
    Scan active tickets for first-response breach, resolution warning, and resolution breach,
    then auto-close stale RESOLVED tickets.
    """
    current = ensure_utc(now) or datetime.now(timezone.utc)

    stmt = (
        select(Ticket)
        .options(selectinload(Ticket.sla_policy))
        .where(
            Ticket.status.notin_(list(TERMINAL_OR_PAUSED_STATUSES)),
            Ticket.sla_paused_at.is_(None),
        )
    )
    if db.bind and db.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)

    tickets = list((await db.execute(stmt)).scalars().all())
    warnings = 0
    breaches = 0
    alert_events: list[tuple[Ticket, str, str]] = []

    for t in tickets:
        # Check first response breach
        if (
            t.first_responded_at is None
            and not t.is_response_breached
            and t.first_response_due_at is not None
            and current > ensure_utc(t.first_response_due_at)
        ):
            t.is_response_breached = True
            breaches += 1
            msg = f"Ticket {t.ticket_code} quá hạn phản hồi đầu tiên"
            emit_outbox_event(
                db=db,
                ticket=t,
                actor=None,
                event_type="SLA_RESPONSE_BREACHED",
                summary=msg,
                details={"first_response_due_at": t.first_response_due_at.isoformat()},
            )
            alert_events.append((t, "TICKET_UPDATED", msg))

        # Check resolution warning & breach
        if not t.is_resolution_breached and t.resolution_due_at is not None:
            res_due = ensure_utc(t.resolution_due_at)
            if current > res_due:
                t.is_resolution_breached = True
                breaches += 1
                msg = f"CẢNH BÁO ĐỎ: Ticket {t.ticket_code} đã vi phạm SLA xử lý"
                emit_outbox_event(
                    db=db,
                    ticket=t,
                    actor=None,
                    event_type="SLA_BREACHED",
                    summary=msg,
                    details={"resolution_due_at": t.resolution_due_at.isoformat()},
                )
                alert_events.append((t, "TICKET_UPDATED", msg))
            elif not t.sla_warning_sent:
                eval_res = evaluate_ticket_sla(t, current)
                if eval_res["state"] == "WARNING":
                    t.sla_warning_sent = True
                    warnings += 1
                    msg = f"Cảnh báo sắp chạm hạn SLA cho ticket {t.ticket_code}"
                    emit_outbox_event(
                        db=db,
                        ticket=t,
                        actor=None,
                        event_type="SLA_WARNING",
                        summary=msg,
                        details={
                            "remaining_seconds": eval_res["remaining_seconds"],
                            "elapsed_pct": eval_res["elapsed_pct"],
                        },
                    )
                    alert_events.append((t, "TICKET_UPDATED", msg))

    if warnings > 0 or breaches > 0:
        await db.commit()
        for t, ev_type, summary in alert_events:
            await ws_manager.broadcast_ticket_event(
                ev_type,
                str(t.id),
                str(t.requester_id),
                payload={
                    "ticket_code": t.ticket_code,
                    "title": t.title,
                    "priority": t.priority.value,
                    "summary": summary,
                },
            )
        logger.info("SLA scanner finished: %d warnings, %d breaches", warnings, breaches)
    else:
        await db.rollback()

    auto_closed = await auto_close_stale_resolved_tickets(db, current)
    return {"warnings": warnings, "breaches": breaches, "auto_closed": auto_closed}
