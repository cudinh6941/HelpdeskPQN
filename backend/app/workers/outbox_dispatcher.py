from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import logging
from typing import Optional

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.models import OutboxEvent, OutboxStatus

logger = logging.getLogger(__name__)
MAX_RETRIES = 5


def compute_webhook_signature(body_bytes: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()


async def dispatch_pending_outbox_batch(
    db: AsyncSession,
    batch_size: int = 20,
    http_client: Optional[httpx.AsyncClient] = None,
) -> int:
    """
    Claim and dispatch pending outbox events to n8n webhook.
    Uses SELECT ... FOR UPDATE SKIP LOCKED on PostgreSQL to prevent duplicate delivery.
    Returns number of events processed in this batch.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)

    stmt = (
        select(OutboxEvent)
        .where(
            OutboxEvent.status == OutboxStatus.PENDING,
            or_(OutboxEvent.next_retry_at.is_(None), OutboxEvent.next_retry_at <= now),
        )
        .order_by(OutboxEvent.created_at)
        .limit(batch_size)
    )
    if db.bind and db.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)

    events = list((await db.execute(stmt)).scalars().all())
    if not events:
        return 0

    for ev in events:
        ev.status = OutboxStatus.PROCESSING
    await db.flush()

    processed_count = 0
    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=10.0)

    try:
        for ev in events:
            envelope = {
                "event_id": str(ev.id),
                "event_type": ev.event_type,
                "aggregate_type": ev.aggregate_type,
                "aggregate_id": str(ev.aggregate_id),
                **ev.payload,
            }
            raw_body = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
            signature = compute_webhook_signature(raw_body, settings.N8N_WEBHOOK_SECRET)

            if settings.N8N_DRY_RUN:
                logger.info(
                    "[Outbox DRY-RUN] Dispatched %s (%s) -> %s",
                    ev.event_type,
                    ev.id,
                    settings.N8N_WEBHOOK_URL,
                )
                ev.status = OutboxStatus.SENT
                ev.processed_at = datetime.now(timezone.utc)
                ev.last_error = None
                processed_count += 1
                continue

            try:
                resp = await client.post(
                    settings.N8N_WEBHOOK_URL,
                    content=raw_body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Helpdesk-Signature": f"sha256={signature}",
                    },
                )
                if 200 <= resp.status_code < 300:
                    ev.status = OutboxStatus.SENT
                    ev.processed_at = datetime.now(timezone.utc)
                    ev.last_error = None
                    processed_count += 1
                else:
                    raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
            except Exception as exc:
                ev.retry_count += 1
                ev.last_error = str(exc)[:1000]
                if ev.retry_count >= MAX_RETRIES:
                    ev.status = OutboxStatus.FAILED
                else:
                    backoff_sec = min(3600, 15 * (2 ** ev.retry_count))
                    ev.status = OutboxStatus.PENDING
                    ev.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=backoff_sec)
                logger.warning("Outbox event %s delivery error (retry %d): %s", ev.id, ev.retry_count, exc)
    finally:
        if owns_client:
            await client.aclose()

    await db.commit()
    return processed_count
