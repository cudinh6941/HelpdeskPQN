from datetime import datetime, timezone
from typing import Any, Optional
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.models import SystemSetting

KEY_AUTO_ASSIGN_ENABLED = "auto_assign_enabled"
KEY_AUTO_CLOSE_RESOLVED_HOURS = "auto_close_resolved_hours"


async def get_automation_settings(db: AsyncSession) -> dict[str, Any]:
    """Read automation settings from DB with env defaults as fallback."""
    defaults = get_settings()
    res = await db.execute(
        select(SystemSetting).where(
            SystemSetting.key.in_([KEY_AUTO_ASSIGN_ENABLED, KEY_AUTO_CLOSE_RESOLVED_HOURS])
        )
    )
    rows = {row.key: row.value for row in res.scalars().all()}

    auto_assign = defaults.AUTO_ASSIGN_ENABLED
    if KEY_AUTO_ASSIGN_ENABLED in rows and isinstance(rows[KEY_AUTO_ASSIGN_ENABLED], dict):
        if "value" in rows[KEY_AUTO_ASSIGN_ENABLED]:
            auto_assign = bool(rows[KEY_AUTO_ASSIGN_ENABLED]["value"])

    auto_close_hours = defaults.AUTO_CLOSE_RESOLVED_HOURS
    if KEY_AUTO_CLOSE_RESOLVED_HOURS in rows and isinstance(rows[KEY_AUTO_CLOSE_RESOLVED_HOURS], dict):
        if "value" in rows[KEY_AUTO_CLOSE_RESOLVED_HOURS]:
            auto_close_hours = int(rows[KEY_AUTO_CLOSE_RESOLVED_HOURS]["value"])

    return {
        "auto_assign_enabled": auto_assign,
        "auto_close_resolved_hours": auto_close_hours,
    }


async def update_automation_settings(
    db: AsyncSession,
    auto_assign_enabled: Optional[bool] = None,
    auto_close_resolved_hours: Optional[int] = None,
    actor_id: Optional[uuid.UUID] = None,
) -> dict[str, Any]:
    """Persist automation settings in system_settings so backend and worker stay synchronized."""
    now = datetime.now(timezone.utc)
    updates: dict[str, Any] = {}
    if auto_assign_enabled is not None:
        updates[KEY_AUTO_ASSIGN_ENABLED] = bool(auto_assign_enabled)
    if auto_close_resolved_hours is not None:
        updates[KEY_AUTO_CLOSE_RESOLVED_HOURS] = int(auto_close_resolved_hours)

    if updates:
        res = await db.execute(
            select(SystemSetting).where(SystemSetting.key.in_(list(updates.keys())))
        )
        existing = {row.key: row for row in res.scalars().all()}
        for key, val in updates.items():
            row = existing.get(key)
            if row is None:
                db.add(
                    SystemSetting(
                        key=key,
                        value={"value": val},
                        updated_by_id=actor_id,
                        updated_at=now,
                    )
                )
            else:
                row.value = {"value": val}
                row.updated_by_id = actor_id
                row.updated_at = now
        await db.commit()

    return await get_automation_settings(db)

