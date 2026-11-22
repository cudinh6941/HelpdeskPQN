from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.attachments import serialize_attachment
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.ws_manager import ws_manager
from app.models.models import (
    Ticket,
    TicketAttachment,
    TicketComment,
    TicketStatus,
    User,
    UserRole,
)
from app.schemas.schemas import CommentCreate, CommentOut
from app.services.notification_service import create_ticket_notifications
from app.services.outbox_writer import emit_outbox_event
from app.services.sla_engine import resume_ticket_sla
from app.services.ticket_state_machine import IT_ROLES, stamp_first_response_if_needed
from app.services.ultraview_service import extract_ultraview_credentials

router = APIRouter(prefix="/tickets", tags=["Ticket Comments"])


@router.post("/{ticket_id}/comments", response_model=CommentOut, status_code=status.HTTP_201_CREATED)
async def add_ticket_comment(
    ticket_id: uuid.UUID,
    payload: CommentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = res.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy ticket.")

    if current_user.role == UserRole.END_USER and ticket.requester_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bạn không có quyền bình luận vào ticket này.")

    if payload.is_internal and current_user.role not in IT_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ nhân viên IT mới được tạo ghi chú nội bộ.",
        )

    now = datetime.now(timezone.utc)
    comment = TicketComment(
        ticket_id=ticket.id,
        author_id=current_user.id,
        body=payload.body.strip(),
        is_internal=payload.is_internal,
        created_at=now,
        updated_at=now,
    )
    db.add(comment)
    await db.flush()

    if payload.attachment_ids:
        att_res = await db.execute(
            select(TicketAttachment).where(TicketAttachment.id.in_(payload.attachment_ids))
        )
        for att in att_res.scalars().all():
            if att.uploader_id == current_user.id or current_user.role in IT_ROLES:
                att.ticket_id = ticket.id
                att.comment_id = comment.id

    resumed_seconds = 0
    if (
        not payload.is_internal
        and current_user.id == ticket.requester_id
        and ticket.status == TicketStatus.WAITING_FOR_USER
    ):
        resumed_seconds = resume_ticket_sla(ticket, now)
        ticket.status = TicketStatus.IN_PROGRESS
        ticket.updated_at = now

    if not payload.is_internal:
        stamp_first_response_if_needed(ticket, current_user, now)
        detected_uv = extract_ultraview_credentials(comment.body)
        if detected_uv:
            ticket.custom_data = {
                **(ticket.custom_data or {}),
                "ultraview": {
                    "id": detected_uv["id"],
                    "pass": detected_uv["pass"],
                    "state": "READY",
                    "updated_at": now.isoformat(),
                },
            }

    emit_outbox_event(
        db=db,
        ticket=ticket,
        actor=current_user,
        event_type="INTERNAL_NOTE_ADDED" if payload.is_internal else "COMMENT_ADDED",
        summary=(
            f"{current_user.full_name} thêm ghi chú nội bộ"
            if payload.is_internal
            else f"{current_user.full_name} đã phản hồi"
        ),
        details={
            "comment_id": str(comment.id),
            "body_preview": comment.body[:160],
            "resumed_sla_seconds": resumed_seconds,
        },
        is_internal=payload.is_internal,
    )
    await create_ticket_notifications(
        db=db,
        ticket=ticket,
        event_type="INTERNAL_NOTE_ADDED" if payload.is_internal else "COMMENT_ADDED",
        title=(
            f"Ghi chú nội bộ: {ticket.ticket_code}"
            if payload.is_internal
            else f"Phản hồi mới: {ticket.ticket_code}"
        ),
        body=(
            f"{current_user.full_name} ghi chú nội bộ: {comment.body[:120]}"
            if payload.is_internal
            else f"{current_user.full_name}: {comment.body[:120]}"
        ),
        actor_id=current_user.id,
        is_internal=payload.is_internal,
    )

    await db.commit()
    await ws_manager.broadcast_ticket_event(
        "COMMENT_ADDED",
        str(ticket.id),
        str(ticket.requester_id),
        is_internal=payload.is_internal,
        payload={
            "comment_id": str(comment.id),
            "ticket_code": ticket.ticket_code,
            "title": ticket.title,
            "priority": ticket.priority.value,
            "actor_id": str(current_user.id),
            "actor_name": current_user.full_name,
            "summary": (
                f"{current_user.full_name} ghi chú nội bộ ở {ticket.ticket_code}"
                if payload.is_internal
                else f"{current_user.full_name} nhắn trong {ticket.ticket_code}"
            ),
        },
    )

    loaded_res = await db.execute(
        select(TicketComment)
        .options(selectinload(TicketComment.author), selectinload(TicketComment.attachments))
        .where(TicketComment.id == comment.id)
    )
    loaded = loaded_res.scalar_one()
    return CommentOut(
        id=loaded.id,
        ticket_id=loaded.ticket_id,
        author_id=loaded.author_id,
        author=loaded.author,
        body=loaded.body,
        is_internal=loaded.is_internal,
        created_at=loaded.created_at,
        attachments=[serialize_attachment(a) for a in loaded.attachments],
    )
