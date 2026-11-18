from collections import Counter, defaultdict
import csv
from datetime import date, datetime, time, timezone
from io import BytesIO, StringIO
import json
from typing import Any, Literal, Optional
import uuid

from fastapi import APIRouter, Depends, Query, Response
from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import require_roles
from app.models.models import Ticket, TicketPriority, TicketStatus, User, UserRole
from app.schemas.schemas import AnalyticsSummaryOut
from app.services.sla_engine import ensure_utc

router = APIRouter(prefix="/analytics", tags=["Analytics & SLA Reporting"])

IT_ANALYTICS_GUARD = require_roles(UserRole.IT_AGENT, UserRole.IT_LEAD, UserRole.SYS_ADMIN)


async def _load_filtered_tickets(
    db: AsyncSession,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    support_group_id: Optional[uuid.UUID] = None,
    priority: Optional[TicketPriority] = None,
) -> list[Ticket]:
    filters = []
    if date_from is not None:
        filters.append(
            Ticket.created_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc)
        )
    if date_to is not None:
        filters.append(
            Ticket.created_at <= datetime.combine(date_to, time.max, tzinfo=timezone.utc)
        )
    if support_group_id is not None:
        filters.append(Ticket.support_group_id == support_group_id)
    if priority is not None:
        filters.append(Ticket.priority == priority)

    stmt = (
        select(Ticket)
        .options(
            selectinload(Ticket.category),
            selectinload(Ticket.support_group),
            selectinload(Ticket.requester),
            selectinload(Ticket.assignee),
        )
        .where(*filters)
        .order_by(desc(Ticket.created_at))
    )
    res = await db.execute(stmt)
    return list(res.scalars().all())


def _compute_summary(tickets: list[Ticket]) -> AnalyticsSummaryOut:
    total = len(tickets)

    by_status: dict[str, int] = Counter()
    by_priority: dict[str, int] = Counter()
    by_category_map: dict[str, int] = defaultdict(int)
    by_group_map: dict[str, int] = defaultdict(int)
    asset_map: dict[str, int] = defaultdict(int)

    agent_stats: dict[str, dict[str, Any]] = {}
    daily_map: dict[str, dict[str, int]] = defaultdict(
        lambda: {"created_count": 0, "resolved_count": 0, "breached_count": 0}
    )

    open_count = 0
    resolved_count = 0
    breached_count = 0
    resolution_minutes_list: list[float] = []
    first_resp_minutes_list: list[float] = []
    ratings: list[int] = []

    closed_statuses = {TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.CANCELLED}

    for t in tickets:
        by_status[t.status.value] += 1
        by_priority[t.priority.value] += 1

        is_resolved = t.status in (TicketStatus.RESOLVED, TicketStatus.CLOSED)
        is_breached = bool(t.is_resolution_breached or t.is_response_breached)

        if t.status in closed_statuses:
            if is_resolved:
                resolved_count += 1
        else:
            open_count += 1

        if is_breached:
            breached_count += 1

        cat_name = t.category.name if t.category else "Khác"
        by_category_map[cat_name] += 1

        grp_name = t.support_group.name if t.support_group else "Chưa phân nhóm"
        by_group_map[grp_name] += 1

        if t.asset_code:
            asset_map[t.asset_code] += 1

        if t.rating is not None:
            ratings.append(t.rating)

        created = ensure_utc(t.created_at)
        if created:
            day_key = created.date().isoformat()
            daily_map[day_key]["created_count"] += 1
            if is_breached:
                daily_map[day_key]["breached_count"] += 1

        effective_res_mins: Optional[float] = None
        if t.resolved_at and created:
            resolved = ensure_utc(t.resolved_at)
            effective_secs = max(
                0.0, (resolved - created).total_seconds() - (t.total_paused_seconds or 0)
            )
            effective_res_mins = effective_secs / 60.0
            resolution_minutes_list.append(effective_res_mins)
            daily_map[resolved.date().isoformat()]["resolved_count"] += 1

        if t.first_responded_at and created:
            first_resp = ensure_utc(t.first_responded_at)
            resp_secs = max(0.0, (first_resp - created).total_seconds())
            first_resp_minutes_list.append(resp_secs / 60.0)

        agent_name = t.assignee.full_name if t.assignee else "Chưa phân công"
        if agent_name not in agent_stats:
            agent_stats[agent_name] = {
                "agent_name": agent_name,
                "assigned_count": 0,
                "resolved_count": 0,
                "breached_count": 0,
                "_res_mins": [],
            }
        agent_stats[agent_name]["assigned_count"] += 1
        if is_resolved:
            agent_stats[agent_name]["resolved_count"] += 1
        if is_breached:
            agent_stats[agent_name]["breached_count"] += 1
        if effective_res_mins is not None:
            agent_stats[agent_name]["_res_mins"].append(effective_res_mins)

    sla_compliance = (
        round(((total - breached_count) / total) * 100.0, 1) if total > 0 else 100.0
    )
    avg_res = (
        round(sum(resolution_minutes_list) / len(resolution_minutes_list), 1)
        if resolution_minutes_list
        else 0.0
    )
    avg_resp = (
        round(sum(first_resp_minutes_list) / len(first_resp_minutes_list), 1)
        if first_resp_minutes_list
        else 0.0
    )
    avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else 0.0

    by_category = [
        {"name": k, "count": v}
        for k, v in sorted(by_category_map.items(), key=lambda x: x[1], reverse=True)
    ]
    by_group = [
        {"name": k, "count": v}
        for k, v in sorted(by_group_map.items(), key=lambda x: x[1], reverse=True)
    ]
    top_assets = [
        {"asset_code": k, "count": v}
        for k, v in sorted(asset_map.items(), key=lambda x: x[1], reverse=True)[:10]
    ]

    by_agent = []
    for entry in agent_stats.values():
        mins = entry.pop("_res_mins")
        entry["avg_resolution_minutes"] = round(sum(mins) / len(mins), 1) if mins else 0.0
        by_agent.append(entry)
    by_agent.sort(key=lambda x: x["assigned_count"], reverse=True)

    daily_trend = [
        {"date": day, **counts}
        for day, counts in sorted(daily_map.items(), key=lambda x: x[0])[-14:]
    ]

    return AnalyticsSummaryOut(
        total_tickets=total,
        open_tickets=open_count,
        resolved_tickets=resolved_count,
        breached_tickets=breached_count,
        sla_compliance_pct=sla_compliance,
        avg_resolution_minutes=avg_res,
        avg_first_response_minutes=avg_resp,
        avg_rating=avg_rating,
        rated_count=len(ratings),
        by_status=dict(by_status),
        by_priority=dict(by_priority),
        by_category=by_category,
        by_group=by_group,
        by_agent=by_agent,
        daily_trend=daily_trend,
        top_assets=top_assets,
    )


@router.get("/summary", response_model=AnalyticsSummaryOut)
async def get_analytics_summary(
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    support_group_id: Optional[uuid.UUID] = Query(default=None),
    priority: Optional[TicketPriority] = Query(default=None),
    _: User = Depends(IT_ANALYTICS_GUARD),
    db: AsyncSession = Depends(get_db),
):
    tickets = await _load_filtered_tickets(
        db,
        date_from=date_from,
        date_to=date_to,
        support_group_id=support_group_id,
        priority=priority,
    )
    return _compute_summary(tickets)


def _ticket_export_row(t: Ticket) -> dict[str, Any]:
    return {
        "ticket_code": t.ticket_code,
        "title": t.title,
        "status": t.status.value,
        "priority": t.priority.value,
        "category": t.category.name if t.category else "",
        "support_group": t.support_group.name if t.support_group else "",
        "requester": t.requester.full_name if t.requester else "",
        "requester_email": t.requester.email if t.requester else "",
        "assignee": t.assignee.full_name if t.assignee else "",
        "asset_code": t.asset_code or "",
        "created_at": t.created_at.isoformat() if t.created_at else "",
        "first_responded_at": t.first_responded_at.isoformat() if t.first_responded_at else "",
        "resolved_at": t.resolved_at.isoformat() if t.resolved_at else "",
        "resolution_due_at": t.resolution_due_at.isoformat() if t.resolution_due_at else "",
        "paused_minutes": round((t.total_paused_seconds or 0) / 60.0, 1),
        "is_response_breached": "YES" if t.is_response_breached else "NO",
        "is_resolution_breached": "YES" if t.is_resolution_breached else "NO",
        "rating": t.rating if t.rating is not None else "",
        "feedback": t.feedback or "",
    }


EXPORT_COLUMNS = [
    ("ticket_code", "Ticket Code"),
    ("title", "Title"),
    ("status", "Status"),
    ("priority", "Priority"),
    ("category", "Category"),
    ("support_group", "Support Group"),
    ("requester", "Requester"),
    ("requester_email", "Requester Email"),
    ("assignee", "Assignee"),
    ("asset_code", "Asset Code"),
    ("created_at", "Created At"),
    ("first_responded_at", "First Responded At"),
    ("resolved_at", "Resolved At"),
    ("resolution_due_at", "Resolution Due At"),
    ("paused_minutes", "Paused Minutes"),
    ("is_response_breached", "Response Breached"),
    ("is_resolution_breached", "Resolution Breached"),
    ("rating", "Rating"),
    ("feedback", "Feedback"),
]


@router.get("/export")
async def export_analytics_report(
    format: Literal["csv", "xlsx", "json"] = Query(default="csv"),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    support_group_id: Optional[uuid.UUID] = Query(default=None),
    priority: Optional[TicketPriority] = Query(default=None),
    _: User = Depends(IT_ANALYTICS_GUARD),
    db: AsyncSession = Depends(get_db),
):
    tickets = await _load_filtered_tickets(
        db,
        date_from=date_from,
        date_to=date_to,
        support_group_id=support_group_id,
        priority=priority,
    )
    summary = _compute_summary(tickets)
    rows = [_ticket_export_row(t) for t in tickets]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")

    if format == "json":
        payload = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "filters": {
                "date_from": date_from.isoformat() if date_from else None,
                "date_to": date_to.isoformat() if date_to else None,
                "support_group_id": str(support_group_id) if support_group_id else None,
                "priority": priority.value if priority else None,
            },
            "summary": summary.model_dump(),
            "tickets": rows,
        }
        return Response(
            content=json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
            media_type="application/json; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="helpdesk-report-{stamp}.json"'
            },
        )

    if format == "xlsx":
        wb = Workbook()
        ws_sum = wb.active
        ws_sum.title = "Summary"
        bold = Font(bold=True)

        ws_sum.append(["IT Helpdesk Operational Report", f"Generated {stamp}"])
        ws_sum["A1"].font = bold
        ws_sum.append([])
        ws_sum.append(["Metric", "Value"])
        ws_sum["A3"].font = bold
        ws_sum["B3"].font = bold
        ws_sum.append(["Total Tickets", summary.total_tickets])
        ws_sum.append(["Open Tickets", summary.open_tickets])
        ws_sum.append(["Resolved / Closed Tickets", summary.resolved_tickets])
        ws_sum.append(["SLA Breached Tickets", summary.breached_tickets])
        ws_sum.append(["SLA Compliance (%)", summary.sla_compliance_pct])
        ws_sum.append(["Avg First Response (min)", summary.avg_first_response_minutes])
        ws_sum.append(["Avg Resolution MTTR (min)", summary.avg_resolution_minutes])
        ws_sum.append(["Avg CSAT Rating (1-5)", summary.avg_rating])

        ws_sum.append([])
        ws_sum.append(["Agent", "Assigned", "Resolved", "Breached", "Avg MTTR (min)"])
        hdr_row = ws_sum.max_row
        for col_idx in range(1, 6):
            ws_sum.cell(row=hdr_row, column=col_idx).font = bold
        for ag in summary.by_agent:
            ws_sum.append(
                [
                    ag["agent_name"],
                    ag["assigned_count"],
                    ag["resolved_count"],
                    ag["breached_count"],
                    ag["avg_resolution_minutes"],
                ]
            )

        ws_sum.column_dimensions["A"].width = 30
        ws_sum.column_dimensions["B"].width = 18
        ws_sum.column_dimensions["C"].width = 14
        ws_sum.column_dimensions["D"].width = 14
        ws_sum.column_dimensions["E"].width = 18

        ws_tickets = wb.create_sheet("Tickets")
        ws_tickets.append([label for _, label in EXPORT_COLUMNS])
        for cell in ws_tickets[1]:
            cell.font = bold
        ws_tickets.freeze_panes = "A2"

        for r in rows:
            ws_tickets.append([r[key] for key, _ in EXPORT_COLUMNS])

        for col in ws_tickets.columns:
            max_len = max((len(str(c.value or "")) for c in col), default=10)
            ws_tickets.column_dimensions[col[0].column_letter].width = min(46, max(12, max_len + 3))

        buf = BytesIO()
        wb.save(buf)
        return Response(
            content=buf.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="helpdesk-report-{stamp}.xlsx"'
            },
        )

    # Default: CSV with UTF-8 BOM for Microsoft Excel Vietnamese support
    csv_buf = StringIO()
    writer = csv.writer(csv_buf)
    writer.writerow([label for _, label in EXPORT_COLUMNS])
    for r in rows:
        writer.writerow([r[key] for key, _ in EXPORT_COLUMNS])

    return Response(
        content=csv_buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="helpdesk-report-{stamp}.csv"'
        },
    )
