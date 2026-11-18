from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.models.models import BusinessCalendar, Ticket, TicketStatus


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _get_tz(tz_name: str):
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        if tz_name in ("Asia/Ho_Chi_Minh", "Asia/Saigon"):
            return timezone(timedelta(hours=7))
        return timezone.utc


def _parse_hhmm(value: str) -> time:
    hh, mm = value.split(":", 1)
    return time(hour=int(hh), minute=int(mm))


def calculate_due_date(
    start_time: datetime,
    duration_minutes: int,
    calendar: Optional[BusinessCalendar],
    business_hours_only: bool,
) -> datetime:
    """
    Calculate SLA deadline in UTC.
    When business_hours_only is True and a BusinessCalendar is configured,
    only minutes inside configured work_days windows (excluding holidays) count.
    """
    start_utc = ensure_utc(start_time) or datetime.now(timezone.utc)
    if duration_minutes <= 0:
        return start_utc

    if not business_hours_only or calendar is None or not calendar.work_days:
        return start_utc + timedelta(minutes=duration_minutes)

    local_tz = _get_tz(calendar.timezone or "Asia/Ho_Chi_Minh")
    cursor = start_utc.astimezone(local_tz)
    holidays: set[str] = set(calendar.holidays or [])
    work_days: dict[str, list[str]] = calendar.work_days or {}

    remaining_seconds = duration_minutes * 60
    guard_days = 0

    while remaining_seconds > 0 and guard_days < 365:
        guard_days += 1
        day_key = str(cursor.weekday())
        date_str = cursor.date().isoformat()
        window = work_days.get(day_key)

        if not window or len(window) < 2 or date_str in holidays:
            next_date = cursor.date() + timedelta(days=1)
            cursor = datetime.combine(next_date, time(0, 0), tzinfo=local_tz)
            continue

        win_start = datetime.combine(cursor.date(), _parse_hhmm(window[0]), tzinfo=local_tz)
        win_end = datetime.combine(cursor.date(), _parse_hhmm(window[1]), tzinfo=local_tz)

        if cursor < win_start:
            cursor = win_start

        if cursor >= win_end:
            next_date = cursor.date() + timedelta(days=1)
            cursor = datetime.combine(next_date, time(0, 0), tzinfo=local_tz)
            continue

        available_seconds = int((win_end - cursor).total_seconds())
        if available_seconds >= remaining_seconds:
            cursor = cursor + timedelta(seconds=remaining_seconds)
            remaining_seconds = 0
        else:
            remaining_seconds -= available_seconds
            next_date = cursor.date() + timedelta(days=1)
            cursor = datetime.combine(next_date, time(0, 0), tzinfo=local_tz)

    return cursor.astimezone(timezone.utc)


def pause_ticket_sla(ticket: Ticket, now: Optional[datetime] = None) -> None:
    """Pause resolution SLA clock when ticket transitions to WAITING_FOR_USER."""
    current = ensure_utc(now) or datetime.now(timezone.utc)
    if ticket.sla_paused_at is None:
        ticket.sla_paused_at = current


def resume_ticket_sla(ticket: Ticket, now: Optional[datetime] = None) -> int:
    """
    Resume resolution SLA clock when ticket leaves WAITING_FOR_USER.
    Adds paused duration to total_paused_seconds and extends resolution_due_at.
    Returns number of seconds paused in this interval.
    """
    if ticket.sla_paused_at is None:
        return 0

    current = ensure_utc(now) or datetime.now(timezone.utc)
    paused_at = ensure_utc(ticket.sla_paused_at)
    paused_seconds = max(0, int((current - paused_at).total_seconds()))

    ticket.total_paused_seconds = (ticket.total_paused_seconds or 0) + paused_seconds
    if ticket.resolution_due_at is not None:
        due_utc = ensure_utc(ticket.resolution_due_at)
        ticket.resolution_due_at = due_utc + timedelta(seconds=paused_seconds)

    ticket.sla_paused_at = None
    return paused_seconds


def evaluate_ticket_sla(ticket: Ticket, now: Optional[datetime] = None) -> dict:
    """Compute real-time SLA status indicator and remaining seconds for UI/API."""
    current = ensure_utc(now) or datetime.now(timezone.utc)
    due = ensure_utc(ticket.resolution_due_at)
    created = ensure_utc(ticket.created_at) or current

    if ticket.status in (TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.CANCELLED):
        state = "BREACHED" if ticket.is_resolution_breached else "MET"
        return {
            "state": state,
            "remaining_seconds": 0,
            "elapsed_pct": 100,
            "is_paused": False,
        }

    if ticket.sla_paused_at is not None:
        paused_at = ensure_utc(ticket.sla_paused_at)
        remaining = int((due - paused_at).total_seconds()) if due else None
        return {
            "state": "PAUSED",
            "remaining_seconds": remaining,
            "elapsed_pct": 0 if remaining is None else None,
            "is_paused": True,
        }

    if due is None:
        return {
            "state": "ON_TRACK",
            "remaining_seconds": None,
            "elapsed_pct": 0,
            "is_paused": False,
        }

    remaining_seconds = int((due - current).total_seconds())
    total_window = max(1, int((due - created).total_seconds()))
    elapsed = max(0, int((current - created).total_seconds()))
    elapsed_pct = min(100, int((elapsed / total_window) * 100))

    warning_pct = ticket.sla_policy.warning_threshold_pct if ticket.sla_policy else 80

    if ticket.is_resolution_breached or remaining_seconds <= 0:
        state = "BREACHED"
    elif elapsed_pct >= warning_pct:
        state = "WARNING"
    else:
        state = "ON_TRACK"

    return {
        "state": state,
        "remaining_seconds": remaining_seconds,
        "elapsed_pct": elapsed_pct,
        "is_paused": False,
    }
