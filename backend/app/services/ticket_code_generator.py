from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Ticket


async def generate_ticket_code(db: AsyncSession) -> str:
    """
    Generate human-friendly ticket code like HD-2026-0001.
    Checks the highest existing code for the current year so it remains
    safe and consistent on both PostgreSQL and SQLite.
    """
    year = datetime.now(timezone.utc).year
    prefix = f"HD-{year}-"
    res = await db.execute(
        select(func.max(Ticket.ticket_code)).where(Ticket.ticket_code.like(f"{prefix}%"))
    )
    latest_code = res.scalar_one_or_none()
    if not latest_code:
        seq = 1
    else:
        try:
            seq = int(latest_code.rsplit("-", 1)[-1]) + 1
        except ValueError:
            seq = 1
    return f"{prefix}{seq:04d}"
