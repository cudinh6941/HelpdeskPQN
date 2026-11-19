from datetime import datetime, timezone
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.attachments import serialize_attachment
from app.core.config import get_settings
from app.core.database import get_db
from app.core.minio_client import storage_service
from app.core.security import get_current_user, require_roles
from app.core.uuid_utils import uuid7
from app.models.models import (
    Category,
    KbArticle,
    KbVisibility,
    Ticket,
    TicketAttachment,
    User,
    UserRole,
)
from app.schemas.schemas import (
    KbArticleCreateRequest,
    KbArticleDetailOut,
    KbArticleListResponse,
    KbArticleUpdateRequest,
)
from app.services.ticket_state_machine import IT_ROLES

router = APIRouter(prefix="/kb", tags=["Knowledge Base"])

IT_KB_ROLES = require_roles(UserRole.IT_AGENT, UserRole.IT_LEAD, UserRole.SYS_ADMIN)


def _kb_options():
    return [
        selectinload(KbArticle.category),
        selectinload(KbArticle.source_ticket),
        selectinload(KbArticle.author),
        selectinload(KbArticle.updated_by),
        selectinload(KbArticle.attachments),
    ]


def _serialize_kb(article: KbArticle) -> KbArticleDetailOut:
    data = KbArticleDetailOut.model_validate(article)
    data.attachments = [
        serialize_attachment(att)
        for att in sorted(article.attachments or [], key=lambda a: a.created_at)
    ]
    return data


async def _link_attachments(
    db: AsyncSession,
    article: KbArticle,
    attachment_ids: list[uuid.UUID],
    current_user: User,
) -> None:
    if not attachment_ids:
        return

    res = await db.execute(
        select(TicketAttachment).where(TicketAttachment.id.in_(attachment_ids))
    )
    settings = get_settings()
    for att in res.scalars().all():
        if att.kb_article_id == article.id:
            continue
        if att.ticket_id is None and att.comment_id is None and att.kb_article_id is None:
            att.kb_article_id = article.id
        else:
            # Clone storage object so KB attachments stay independent of the source ticket
            raw = storage_service.get_object_bytes(att.object_key)
            if raw is None:
                continue
            new_id = uuid7()
            date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")
            new_key = f"kb/{date_prefix}/{new_id}_{att.file_name}"
            storage_service.put_object_bytes(new_key, raw, att.content_type)
            db.add(
                TicketAttachment(
                    id=new_id,
                    kb_article_id=article.id,
                    uploader_id=current_user.id,
                    bucket_name=settings.MINIO_BUCKET,
                    object_key=new_key,
                    file_name=att.file_name,
                    content_type=att.content_type,
                    size_bytes=len(raw),
                    is_uploaded=True,
                )
            )


def _matches_query(article: KbArticle, q_lower: str) -> bool:
    haystack = " ".join(
        [
            article.title or "",
            article.symptoms or "",
            article.root_cause or "",
            article.notes or "",
            " ".join(article.keywords or []),
            " ".join(article.steps or []),
        ]
    ).lower()
    return q_lower in haystack


@router.get("", response_model=KbArticleListResponse)
async def list_kb_articles(
    q: Optional[str] = Query(default=None),
    category_id: Optional[uuid.UUID] = Query(default=None),
    visibility: Optional[KbVisibility] = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    filters = [KbArticle.is_active == True]

    if current_user.role not in IT_ROLES:
        filters.append(KbArticle.visibility == KbVisibility.PUBLIC)
    elif visibility is not None:
        filters.append(KbArticle.visibility == visibility)

    if category_id is not None:
        filters.append(KbArticle.category_id == category_id)

    stmt = (
        select(KbArticle)
        .options(*_kb_options())
        .where(*filters)
        .order_by(desc(KbArticle.updated_at))
    )
    rows = list((await db.execute(stmt)).scalars().all())

    if q and q.strip():
        q_lower = q.strip().lower()
        rows = [r for r in rows if _matches_query(r, q_lower)]

    return KbArticleListResponse(items=[_serialize_kb(r) for r in rows], total=len(rows))


@router.get("/{article_id}", response_model=KbArticleDetailOut)
async def get_kb_article(
    article_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(KbArticle)
        .options(*_kb_options())
        .where(KbArticle.id == article_id, KbArticle.is_active == True)
    )
    article = res.scalar_one_or_none()
    if article is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy bài viết Knowledge Base.")

    if current_user.role not in IT_ROLES and article.visibility != KbVisibility.PUBLIC:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bài viết này chỉ dành cho đội IT.")

    return _serialize_kb(article)


@router.post("", response_model=KbArticleDetailOut, status_code=status.HTTP_201_CREATED)
async def create_kb_article(
    payload: KbArticleCreateRequest,
    current_user: User = Depends(IT_KB_ROLES),
    db: AsyncSession = Depends(get_db),
):
    if payload.category_id is not None:
        cat = (await db.execute(select(Category).where(Category.id == payload.category_id))).scalar_one_or_none()
        if cat is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy danh mục.")

    if payload.source_ticket_id is not None:
        t = (await db.execute(select(Ticket).where(Ticket.id == payload.source_ticket_id))).scalar_one_or_none()
        if t is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy ticket nguồn.")

    now = datetime.now(timezone.utc)
    article = KbArticle(
        category_id=payload.category_id,
        visibility=payload.visibility,
        title=payload.title.strip(),
        symptoms=payload.symptoms.strip() if payload.symptoms else None,
        root_cause=payload.root_cause.strip() if payload.root_cause else None,
        steps=[s.strip() for s in payload.steps if s and s.strip()],
        notes=payload.notes.strip() if payload.notes else None,
        keywords=[k.strip().lower() for k in payload.keywords if k and k.strip()],
        source_ticket_id=payload.source_ticket_id,
        author_id=current_user.id,
        updated_by_id=current_user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(article)
    await db.flush()

    if payload.attachment_ids:
        await _link_attachments(db, article, payload.attachment_ids, current_user)

    await db.commit()
    return await get_kb_article(article.id, current_user, db)


@router.patch("/{article_id}", response_model=KbArticleDetailOut)
async def update_kb_article(
    article_id: uuid.UUID,
    payload: KbArticleUpdateRequest,
    current_user: User = Depends(IT_KB_ROLES),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(KbArticle)
        .options(selectinload(KbArticle.attachments))
        .where(KbArticle.id == article_id, KbArticle.is_active == True)
    )
    article = res.scalar_one_or_none()
    if article is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy bài viết Knowledge Base.")

    if "category_id" in payload.model_fields_set:
        if payload.category_id is not None:
            cat = (await db.execute(select(Category).where(Category.id == payload.category_id))).scalar_one_or_none()
            if cat is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy danh mục.")
        article.category_id = payload.category_id

    if payload.visibility is not None:
        article.visibility = payload.visibility
    if payload.title is not None:
        article.title = payload.title.strip()
    if "symptoms" in payload.model_fields_set:
        article.symptoms = payload.symptoms.strip() if payload.symptoms else None
    if "root_cause" in payload.model_fields_set:
        article.root_cause = payload.root_cause.strip() if payload.root_cause else None
    if payload.steps is not None:
        article.steps = [s.strip() for s in payload.steps if s and s.strip()]
    if "notes" in payload.model_fields_set:
        article.notes = payload.notes.strip() if payload.notes else None
    if payload.keywords is not None:
        article.keywords = [k.strip().lower() for k in payload.keywords if k and k.strip()]
    if "source_ticket_id" in payload.model_fields_set:
        article.source_ticket_id = payload.source_ticket_id

    if payload.attachment_ids is not None:
        keep_set = set(payload.attachment_ids)
        for existing_att in list(article.attachments):
            if existing_att.id not in keep_set:
                await db.delete(existing_att)
        await _link_attachments(db, article, payload.attachment_ids, current_user)

    article.updated_by_id = current_user.id
    article.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return await get_kb_article(article.id, current_user, db)


@router.delete("/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_kb_article(
    article_id: uuid.UUID,
    _: User = Depends(IT_KB_ROLES),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(KbArticle).where(KbArticle.id == article_id))
    article = res.scalar_one_or_none()
    if article is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy bài viết Knowledge Base.")

    await db.delete(article)
    await db.commit()
