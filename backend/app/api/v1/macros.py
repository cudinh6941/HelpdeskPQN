import re
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_roles
from app.models.models import CannedResponse, Category, User, UserRole
from app.schemas.schemas import CannedResponseCreate, CannedResponseOut, CannedResponseUpdate

router = APIRouter(prefix="/macros", tags=["Canned Responses & Macros"])

IT_GUARD = require_roles(UserRole.IT_AGENT, UserRole.IT_LEAD, UserRole.SYS_ADMIN)
SHORTCUT_PATTERN = re.compile(r"^[a-z0-9_-]+$")


def _normalize_shortcut(raw: str) -> str:
    clean = raw.strip().lstrip("/").lower()
    if not clean or not SHORTCUT_PATTERN.match(clean):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Shortcut chỉ được chứa chữ thường, số, gạch dưới (_) hoặc gạch ngang (-).",
        )
    return clean


@router.get("", response_model=list[CannedResponseOut])
async def list_macros(
    q: Optional[str] = Query(default=None),
    category_id: Optional[uuid.UUID] = Query(default=None),
    _: User = Depends(IT_GUARD),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(CannedResponse).where(CannedResponse.is_active == True)
    if category_id is not None:
        stmt = stmt.where(CannedResponse.category_id == category_id)
    stmt = stmt.order_by(CannedResponse.shortcut)
    rows = list((await db.execute(stmt)).scalars().all())
    if q and q.strip():
        term = q.strip().lower().lstrip("/")
        rows = [
            r
            for r in rows
            if term in r.shortcut.lower()
            or term in r.title.lower()
            or term in r.body.lower()
        ]
    return [CannedResponseOut.model_validate(r) for r in rows]


@router.post("", response_model=CannedResponseOut, status_code=status.HTTP_201_CREATED)
async def create_macro(
    payload: CannedResponseCreate,
    current_user: User = Depends(IT_GUARD),
    db: AsyncSession = Depends(get_db),
):
    shortcut = _normalize_shortcut(payload.shortcut)
    dup = (
        await db.execute(select(CannedResponse).where(CannedResponse.shortcut == shortcut))
    ).scalar_one_or_none()
    if dup is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Shortcut '/{shortcut}' đã tồn tại.",
        )

    if payload.category_id is not None:
        cat = (
            await db.execute(select(Category).where(Category.id == payload.category_id))
        ).scalar_one_or_none()
        if cat is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy danh mục.")

    macro = CannedResponse(
        shortcut=shortcut,
        title=payload.title.strip(),
        body=payload.body.strip(),
        category_id=payload.category_id,
        target_status=payload.target_status,
        is_internal=payload.is_internal,
        created_by_id=current_user.id,
        is_active=True,
    )
    db.add(macro)
    await db.commit()
    await db.refresh(macro)
    return CannedResponseOut.model_validate(macro)


@router.patch("/{macro_id}", response_model=CannedResponseOut)
async def update_macro(
    macro_id: uuid.UUID,
    payload: CannedResponseUpdate,
    _: User = Depends(IT_GUARD),
    db: AsyncSession = Depends(get_db),
):
    macro = (
        await db.execute(select(CannedResponse).where(CannedResponse.id == macro_id))
    ).scalar_one_or_none()
    if macro is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy macro.")

    updates = payload.model_dump(exclude_unset=True)
    if "shortcut" in updates and updates["shortcut"] is not None:
        new_sc = _normalize_shortcut(updates["shortcut"])
        if new_sc != macro.shortcut:
            dup = (
                await db.execute(select(CannedResponse).where(CannedResponse.shortcut == new_sc))
            ).scalar_one_or_none()
            if dup is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Shortcut '/{new_sc}' đã tồn tại.",
                )
        updates["shortcut"] = new_sc

    if "category_id" in updates and updates["category_id"] is not None:
        cat = (
            await db.execute(select(Category).where(Category.id == updates["category_id"]))
        ).scalar_one_or_none()
        if cat is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy danh mục.")

    for k, v in updates.items():
        if k in ("title", "body") and isinstance(v, str):
            v = v.strip()
        setattr(macro, k, v)

    await db.commit()
    await db.refresh(macro)
    return CannedResponseOut.model_validate(macro)


@router.delete("/{macro_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_macro(
    macro_id: uuid.UUID,
    _: User = Depends(IT_GUARD),
    db: AsyncSession = Depends(get_db),
):
    macro = (
        await db.execute(select(CannedResponse).where(CannedResponse.id == macro_id))
    ).scalar_one_or_none()
    if macro is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy macro.")

    await db.delete(macro)
    await db.commit()

