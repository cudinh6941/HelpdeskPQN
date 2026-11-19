from datetime import datetime, timezone
from pathlib import PurePath
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.minio_client import storage_service
from app.core.security import get_current_user
from app.core.uuid_utils import uuid7
from app.models.models import KbArticle, KbVisibility, Ticket, TicketAttachment, User, UserRole
from app.schemas.schemas import AttachmentOut, PresignedUploadRequest, PresignedUploadResponse
from app.services.ticket_state_machine import IT_ROLES

router = APIRouter(prefix="/attachments", tags=["Attachments (MinIO + Ctrl+V Paste)"])


def serialize_attachment(att: TicketAttachment) -> AttachmentOut:
    return AttachmentOut(
        id=att.id,
        ticket_id=att.ticket_id,
        comment_id=att.comment_id,
        kb_article_id=att.kb_article_id,
        file_name=att.file_name,
        content_type=att.content_type,
        size_bytes=att.size_bytes,
        is_uploaded=att.is_uploaded,
        created_at=att.created_at,
        download_url=f"/api/v1/attachments/{att.id}/file",
    )


@router.post("/presigned-upload", response_model=PresignedUploadResponse)
async def create_presigned_upload(
    payload: PresignedUploadRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    safe_name = PurePath(payload.file_name).name or "pasted-image.png"
    att_id = uuid7()
    date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    object_key = f"{date_prefix}/{att_id}_{safe_name}"

    if payload.ticket_id is not None:
        t_res = await db.execute(select(Ticket).where(Ticket.id == payload.ticket_id))
        ticket = t_res.scalar_one_or_none()
        if ticket is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy ticket.")
        if current_user.role == UserRole.END_USER and ticket.requester_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không có quyền đính kèm file vào ticket này.")

    if payload.kb_article_id is not None:
        if current_user.role not in IT_ROLES:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Chỉ đội IT mới được đính kèm ảnh vào Knowledge Base.")
        kb_res = await db.execute(select(KbArticle).where(KbArticle.id == payload.kb_article_id))
        if kb_res.scalar_one_or_none() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy bài viết Knowledge Base.")

    att = TicketAttachment(
        id=att_id,
        ticket_id=payload.ticket_id,
        kb_article_id=payload.kb_article_id,
        uploader_id=current_user.id,
        bucket_name=settings.MINIO_BUCKET,
        object_key=object_key,
        file_name=safe_name,
        content_type=payload.content_type,
        size_bytes=payload.size_bytes,
        is_uploaded=False,
    )
    db.add(att)
    await db.commit()

    presigned = storage_service.presigned_put_url(object_key)
    direct_url = f"/api/v1/attachments/{att.id}/upload"

    return PresignedUploadResponse(
        attachment_id=att.id,
        object_key=object_key,
        upload_url=presigned or direct_url,
        direct_upload_url=direct_url,
        use_presigned=bool(presigned),
    )


@router.put("/{attachment_id}/upload", response_model=AttachmentOut)
async def upload_attachment_raw(
    attachment_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(TicketAttachment).where(TicketAttachment.id == attachment_id))
    att = res.scalar_one_or_none()
    if att is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy bản ghi tệp đính kèm.")
    if att.uploader_id != current_user.id and current_user.role == UserRole.END_USER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không có quyền upload tệp này.")

    data = await request.body()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nội dung file trống.")

    storage_service.put_object_bytes(att.object_key, data, att.content_type)
    att.size_bytes = len(data)
    att.is_uploaded = True
    await db.commit()
    await db.refresh(att)
    return serialize_attachment(att)


@router.post("/{attachment_id}/upload", response_model=AttachmentOut)
async def upload_attachment_multipart(
    attachment_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(TicketAttachment).where(TicketAttachment.id == attachment_id))
    att = res.scalar_one_or_none()
    if att is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy bản ghi tệp đính kèm.")
    if att.uploader_id != current_user.id and current_user.role == UserRole.END_USER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không có quyền upload tệp này.")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nội dung file trống.")

    content_type = file.content_type or att.content_type
    storage_service.put_object_bytes(att.object_key, data, content_type)
    att.size_bytes = len(data)
    att.content_type = content_type
    att.is_uploaded = True
    await db.commit()
    await db.refresh(att)
    return serialize_attachment(att)


async def _resolve_user_from_header_or_query(
    request: Request,
    token: Optional[str],
    db: AsyncSession,
) -> User:
    raw_token = token
    auth_header = request.headers.get("Authorization")
    if not raw_token and auth_header and auth_header.lower().startswith("bearer "):
        raw_token = auth_header.split(" ", 1)[1].strip()

    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Thiếu thông tin xác thực.")

    settings = get_settings()
    try:
        payload = jwt.decode(raw_token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_uuid = uuid.UUID(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token không hợp lệ.")

    res = await db.execute(select(User).where(User.id == user_uuid))
    user = res.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tài khoản không hợp lệ.")
    return user


@router.get("/{attachment_id}/file")
async def download_attachment_file(
    attachment_id: uuid.UUID,
    request: Request,
    token: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    current_user = await _resolve_user_from_header_or_query(request, token, db)

    res = await db.execute(select(TicketAttachment).where(TicketAttachment.id == attachment_id))
    att = res.scalar_one_or_none()
    if att is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy tệp.")

    if current_user.role == UserRole.END_USER and att.ticket_id is not None:
        t_res = await db.execute(select(Ticket).where(Ticket.id == att.ticket_id))
        ticket = t_res.scalar_one_or_none()
        if ticket and ticket.requester_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không có quyền xem tệp này.")

    if current_user.role == UserRole.END_USER and att.kb_article_id is not None:
        kb_res = await db.execute(select(KbArticle).where(KbArticle.id == att.kb_article_id))
        kb = kb_res.scalar_one_or_none()
        if kb and kb.visibility != KbVisibility.PUBLIC:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không có quyền xem tệp nội bộ này.")

    data = storage_service.get_object_bytes(att.object_key)
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dữ liệu file không tồn tại trên Storage.")

    return Response(
        content=data,
        media_type=att.content_type,
        headers={"Content-Disposition": f'inline; filename="{att.file_name}"'},
    )
