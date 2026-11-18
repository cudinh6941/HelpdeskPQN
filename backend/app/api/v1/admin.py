from datetime import datetime, timezone
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import require_roles
from app.core.uuid_utils import uuid7
from app.models.models import (
    Category,
    OutboxEvent,
    OutboxStatus,
    SlaPolicy,
    SupportGroup,
    User,
    UserRole,
)
from app.schemas.schemas import (
    AutomationSettingsOut,
    AutomationSettingsUpdate,
    CategoryCreate,
    CategoryOut,
    CategoryUpdate,
    KbArticleCreate,
    OutboxEventOut,
    SlaPolicyOut,
    SlaPolicyUpdate,
    SupportGroupCreate,
    SupportGroupOut,
    SupportGroupUpdate,
    UserOut,
    UserRoleUpdate,
)
from app.workers.sla_scanner import auto_close_stale_resolved_tickets

router = APIRouter(prefix="/admin", tags=["Administration & Outbox"])

LEAD_OR_ADMIN = require_roles(UserRole.IT_LEAD, UserRole.SYS_ADMIN)
ADMIN_ONLY = require_roles(UserRole.SYS_ADMIN)


@router.get("/categories", response_model=list[CategoryOut])
async def admin_list_categories(
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(Category).order_by(Category.sort_order, Category.name))
    return list(res.scalars().all())


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
async def admin_create_category(
    payload: CategoryCreate,
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    exists = (await db.execute(select(Category).where(Category.slug == payload.slug))).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slug danh mục đã tồn tại.")

    cat = Category(**payload.model_dump())
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return cat


@router.patch("/categories/{category_id}", response_model=CategoryOut)
async def admin_update_category(
    category_id: uuid.UUID,
    payload: CategoryUpdate,
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    cat = (await db.execute(select(Category).where(Category.id == category_id))).scalar_one_or_none()
    if cat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy danh mục.")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(cat, k, v)
    await db.commit()
    await db.refresh(cat)
    return cat


@router.get("/support-groups", response_model=list[SupportGroupOut])
async def admin_list_groups(
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(SupportGroup).order_by(SupportGroup.name))
    return list(res.scalars().all())


@router.post("/support-groups", response_model=SupportGroupOut, status_code=status.HTTP_201_CREATED)
async def admin_create_group(
    payload: SupportGroupCreate,
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    exists = (
        await db.execute(select(SupportGroup).where(SupportGroup.code == payload.code))
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mã nhóm đã tồn tại.")
    group = SupportGroup(**payload.model_dump())
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return group


@router.patch("/support-groups/{group_id}", response_model=SupportGroupOut)
async def admin_update_group(
    group_id: uuid.UUID,
    payload: SupportGroupUpdate,
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    group = (await db.execute(select(SupportGroup).where(SupportGroup.id == group_id))).scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy nhóm.")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(group, k, v)
    await db.commit()
    await db.refresh(group)
    return group


@router.get("/sla-policies", response_model=list[SlaPolicyOut])
async def admin_list_sla_policies(
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(SlaPolicy).order_by(SlaPolicy.resolution_minutes))
    return list(res.scalars().all())


@router.patch("/sla-policies/{policy_id}", response_model=SlaPolicyOut)
async def admin_update_sla_policy(
    policy_id: uuid.UUID,
    payload: SlaPolicyUpdate,
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    policy = (await db.execute(select(SlaPolicy).where(SlaPolicy.id == policy_id))).scalar_one_or_none()
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy SLA policy.")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(policy, k, v)
    await db.commit()
    await db.refresh(policy)
    return policy


@router.get("/users", response_model=list[UserOut])
async def admin_list_users(
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(User).options(selectinload(User.department)).order_by(User.full_name)
    )
    return [UserOut.model_validate(u) for u in res.scalars().all()]


@router.patch("/users/{user_id}", response_model=UserOut)
async def admin_update_user(
    user_id: uuid.UUID,
    payload: UserRoleUpdate,
    _: User = Depends(ADMIN_ONLY),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(User).options(selectinload(User.department)).where(User.id == user_id)
    )
    user = res.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy người dùng.")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(user, k, v)
    await db.commit()
    await db.refresh(user)
    return UserOut.model_validate(user)


@router.get("/outbox-events", response_model=list[OutboxEventOut])
async def admin_list_outbox_events(
    status_filter: Optional[OutboxStatus] = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(OutboxEvent).order_by(desc(OutboxEvent.created_at)).limit(limit)
    if status_filter is not None:
        stmt = stmt.where(OutboxEvent.status == status_filter)
    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.post("/outbox-events/{event_id}/retry", response_model=OutboxEventOut)
async def admin_retry_outbox_event(
    event_id: uuid.UUID,
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    ev = (await db.execute(select(OutboxEvent).where(OutboxEvent.id == event_id))).scalar_one_or_none()
    if ev is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy outbox event.")

    ev.status = OutboxStatus.PENDING
    ev.next_retry_at = datetime.now(timezone.utc)
    ev.last_error = None
    await db.commit()
    await db.refresh(ev)
    return ev


@router.post("/categories/{category_id}/kb", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
async def admin_add_kb_article(
    category_id: uuid.UUID,
    payload: KbArticleCreate,
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    cat = (await db.execute(select(Category).where(Category.id == category_id))).scalar_one_or_none()
    if cat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy danh mục.")

    schema = dict(cat.form_schema or {})
    articles = list(schema.get("kb_articles") or [])
    new_article = {
        "id": f"kb-{str(uuid7())[:8]}",
        "title": payload.title.strip(),
        "keywords": [k.strip().lower() for k in payload.keywords if k.strip()],
        "steps": [s.strip() for s in payload.steps if s.strip()],
    }
    articles.append(new_article)
    cat.form_schema = {**schema, "kb_articles": articles}
    await db.commit()
    await db.refresh(cat)
    return cat


@router.delete("/categories/{category_id}/kb/{article_id}", response_model=CategoryOut)
async def admin_delete_kb_article(
    category_id: uuid.UUID,
    article_id: str,
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    cat = (await db.execute(select(Category).where(Category.id == category_id))).scalar_one_or_none()
    if cat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy danh mục.")

    schema = dict(cat.form_schema or {})
    articles = [a for a in (schema.get("kb_articles") or []) if a.get("id") != article_id]
    cat.form_schema = {**schema, "kb_articles": articles}
    await db.commit()
    await db.refresh(cat)
    return cat


@router.get("/automation-settings", response_model=AutomationSettingsOut)
async def admin_get_automation_settings(_: User = Depends(LEAD_OR_ADMIN)):
    settings = get_settings()
    return AutomationSettingsOut(
        auto_assign_enabled=settings.AUTO_ASSIGN_ENABLED,
        auto_close_resolved_hours=settings.AUTO_CLOSE_RESOLVED_HOURS,
    )


@router.patch("/automation-settings", response_model=AutomationSettingsOut)
async def admin_update_automation_settings(
    payload: AutomationSettingsUpdate,
    _: User = Depends(LEAD_OR_ADMIN),
):
    settings = get_settings()
    if payload.auto_assign_enabled is not None:
        settings.AUTO_ASSIGN_ENABLED = payload.auto_assign_enabled
    if payload.auto_close_resolved_hours is not None:
        settings.AUTO_CLOSE_RESOLVED_HOURS = payload.auto_close_resolved_hours
    return AutomationSettingsOut(
        auto_assign_enabled=settings.AUTO_ASSIGN_ENABLED,
        auto_close_resolved_hours=settings.AUTO_CLOSE_RESOLVED_HOURS,
    )


@router.post("/automation/run-auto-close")
async def admin_run_auto_close_now(
    hours: Optional[int] = Query(default=None, ge=1, le=720),
    _: User = Depends(LEAD_OR_ADMIN),
    db: AsyncSession = Depends(get_db),
):
    count = await auto_close_stale_resolved_tickets(db, max_age_hours=hours)
    return {"auto_closed": count}
