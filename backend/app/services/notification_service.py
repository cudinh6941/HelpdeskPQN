from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Notification, SupportGroupMember, Ticket, User, UserRole

IT_ROLE_VALUES = [UserRole.IT_AGENT, UserRole.IT_LEAD, UserRole.SYS_ADMIN]


async def create_ticket_notifications(
    db: AsyncSession,
    ticket: Ticket,
    event_type: str,
    title: str,
    body: str,
    actor_id: Optional[uuid.UUID] = None,
    is_internal: bool = False,
) -> int:
    """
    Create persistent in-app Notification records in the current DB transaction
    for relevant ticket participants, respecting internal-note RBAC.
    """
    recipients: dict[uuid.UUID, str] = {}
    workspace_link = f"/workspace/tickets/{ticket.id}"
    portal_link = f"/portal/tickets/{ticket.id}"

    if not is_internal and ticket.requester_id != actor_id:
        recipients[ticket.requester_id] = portal_link

    if ticket.assignee_id is not None and ticket.assignee_id != actor_id:
        recipients[ticket.assignee_id] = workspace_link

    needs_group_or_lead = (
        is_internal
        or ticket.assignee_id is None
        or event_type in ("SLA_WARNING", "SLA_BREACHED", "SLA_RESPONSE_BREACHED")
    )

    if needs_group_or_lead:
        group_users: list[uuid.UUID] = []
        if ticket.support_group_id is not None:
            grp_res = await db.execute(
                select(User.id)
                .join(SupportGroupMember, SupportGroupMember.user_id == User.id)
                .where(
                    SupportGroupMember.group_id == ticket.support_group_id,
                    User.is_active == True,
                    User.role.in_(IT_ROLE_VALUES),
                )
            )
            group_users = list(grp_res.scalars().all())

        for uid in group_users:
            if uid != actor_id:
                recipients[uid] = workspace_link

        if event_type in ("SLA_WARNING", "SLA_BREACHED", "SLA_RESPONSE_BREACHED"):
            lead_res = await db.execute(
                select(User.id).where(User.is_active == True, User.role == UserRole.IT_LEAD)
            )
            for uid in lead_res.scalars().all():
                if uid != actor_id:
                    recipients[uid] = workspace_link

        if not group_users and ticket.assignee_id is None:
            fallback_res = await db.execute(
                select(User.id).where(
                    User.is_active == True,
                    User.role.in_([UserRole.IT_AGENT, UserRole.IT_LEAD]),
                )
            )
            for uid in fallback_res.scalars().all():
                if uid != actor_id:
                    recipients[uid] = workspace_link

    if not recipients:
        return 0

    now = datetime.now(timezone.utc)
    clean_title = title.strip()[:200]
    clean_body = body.strip()
    for uid, link_url in recipients.items():
        db.add(
            Notification(
                user_id=uid,
                ticket_id=ticket.id,
                event_type=event_type,
                title=clean_title,
                body=clean_body,
                link_url=link_url,
                is_read=False,
                created_at=now,
            )
        )
    return len(recipients)

