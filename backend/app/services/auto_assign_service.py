from typing import Optional
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    SupportGroupMember,
    Ticket,
    TicketStatus,
    User,
    UserRole,
)

ACTIVE_ASSIGNMENT_STATUSES = [
    TicketStatus.ASSIGNED,
    TicketStatus.IN_PROGRESS,
    TicketStatus.WAITING_FOR_USER,
    TicketStatus.REOPENED,
]


async def pick_least_loaded_agent(
    db: AsyncSession,
    support_group_id: Optional[uuid.UUID],
) -> Optional[User]:
    """
    Pick the active IT agent (or lead) in the target support group who currently
    has the fewest open assigned tickets. Falls back to all active IT agents if
    the group has no explicit members configured.
    """
    candidates: list[User] = []

    if support_group_id is not None:
        grp_stmt = (
            select(User)
            .join(SupportGroupMember, SupportGroupMember.user_id == User.id)
            .where(
                SupportGroupMember.group_id == support_group_id,
                User.is_active == True,
                User.role.in_([UserRole.IT_AGENT, UserRole.IT_LEAD]),
            )
        )
        grp_members = list((await db.execute(grp_stmt)).scalars().all())
        agents_only = [u for u in grp_members if u.role == UserRole.IT_AGENT]
        candidates = agents_only if agents_only else grp_members

    if not candidates:
        fallback_stmt = select(User).where(
            User.is_active == True,
            User.role == UserRole.IT_AGENT,
        )
        candidates = list((await db.execute(fallback_stmt)).scalars().all())

    if not candidates:
        return None

    candidate_ids = [u.id for u in candidates]
    load_stmt = (
        select(Ticket.assignee_id, func.count(Ticket.id))
        .where(
            Ticket.assignee_id.in_(candidate_ids),
            Ticket.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
        )
        .group_by(Ticket.assignee_id)
    )
    load_rows = (await db.execute(load_stmt)).all()
    load_map = {row[0]: int(row[1]) for row in load_rows}

    candidates.sort(key=lambda u: (load_map.get(u.id, 0), str(u.id)))
    return candidates[0]
