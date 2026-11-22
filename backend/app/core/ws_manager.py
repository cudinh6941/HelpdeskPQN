import asyncio
from dataclasses import dataclass
import json
import logging
from typing import Any, Optional

import asyncpg
from fastapi import WebSocket
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.models import UserRole

logger = logging.getLogger(__name__)

IT_WS_ROLES = {UserRole.IT_AGENT, UserRole.IT_LEAD, UserRole.SYS_ADMIN}
WS_NOTIFY_CHANNEL = "helpdesk_ws_events"
MAX_PG_NOTIFY_BYTES = 7500


def _pg_dsn_from_sqlalchemy_url(url: str) -> Optional[str]:
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    if url.startswith("postgresql://"):
        return url
    return None


@dataclass(eq=False)
class _WsClient:
    websocket: WebSocket
    user_id: str
    role: UserRole


class ConnectionManager:
    """In-memory WebSocket connection hub with per-role RBAC event filtering and PG LISTEN/NOTIFY sync."""

    def __init__(self) -> None:
        self._clients: set[_WsClient] = set()
        self._pg_listener_task: Optional[asyncio.Task] = None
        self._pg_listen_enabled: bool = False
        self._bg_tasks: set[asyncio.Task] = set()

    async def connect(self, websocket: WebSocket, user_id: str, role: UserRole) -> _WsClient:
        await websocket.accept()
        client = _WsClient(websocket=websocket, user_id=user_id, role=role)
        self._clients.add(client)
        return client

    def disconnect(self, client: _WsClient) -> None:
        self._clients.discard(client)

    async def start_pg_listener(self) -> None:
        dsn = _pg_dsn_from_sqlalchemy_url(get_settings().DATABASE_URL)
        if dsn is None:
            return
        if self._pg_listener_task is not None and not self._pg_listener_task.done():
            return
        self._pg_listen_enabled = True
        self._pg_listener_task = asyncio.create_task(self._pg_listen_loop(dsn))

    async def stop_pg_listener(self) -> None:
        self._pg_listen_enabled = False
        if self._pg_listener_task is not None:
            self._pg_listener_task.cancel()
            try:
                await self._pg_listener_task
            except asyncio.CancelledError:
                pass
            self._pg_listener_task = None
        for task in list(self._bg_tasks):
            task.cancel()
        self._bg_tasks.clear()

    async def _pg_listen_loop(self, dsn: str) -> None:
        loop = asyncio.get_running_loop()

        def on_notify(_conn, _pid: int, _channel: str, raw_payload: str) -> None:
            try:
                data = json.loads(raw_payload)
            except Exception as exc:
                logger.warning("Invalid WS NOTIFY payload: %s", exc)
                return

            task = loop.create_task(
                self.broadcast_local(
                    event_type=data["event_type"],
                    ticket_id=data["ticket_id"],
                    requester_id=data["requester_id"],
                    is_internal=bool(data.get("is_internal", False)),
                    payload=data.get("payload") or {},
                )
            )
            self._bg_tasks.add(task)

            def _on_done(done_task: asyncio.Task) -> None:
                self._bg_tasks.discard(done_task)
                if not done_task.cancelled():
                    exc = done_task.exception()
                    if exc is not None:
                        logger.warning("Error dispatching WS NOTIFY event: %s", exc)

            task.add_done_callback(_on_done)

        while True:
            conn: Optional[asyncpg.Connection] = None
            try:
                conn = await asyncpg.connect(dsn)
                await conn.add_listener(WS_NOTIFY_CHANNEL, on_notify)
                logger.info("PostgreSQL WebSocket NOTIFY listener started on channel %s", WS_NOTIFY_CHANNEL)
                while True:
                    await asyncio.sleep(30)
                    await conn.execute("SELECT 1")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("PostgreSQL WS listener error, reconnecting in 3s: %s", exc)
                await asyncio.sleep(3)
            finally:
                if conn is not None:
                    try:
                        await conn.close()
                    except Exception:
                        pass

    async def broadcast_local(
        self,
        event_type: str,
        ticket_id: str,
        requester_id: str,
        is_internal: bool = False,
        payload: Optional[dict[str, Any]] = None,
    ) -> None:
        if not self._clients:
            return

        message = {
            "type": event_type,
            "ticket_id": ticket_id,
            "is_internal": is_internal,
            "payload": payload or {},
        }

        stale: list[_WsClient] = []
        for client in list(self._clients):
            # END_USER only receives non-internal events for their own tickets
            if client.role not in IT_WS_ROLES:
                if is_internal or client.user_id != str(requester_id):
                    continue

            try:
                await client.websocket.send_json(message)
            except Exception as exc:
                logger.debug("Removing stale WS client (%s): %s", client.user_id, exc)
                stale.append(client)

        for client in stale:
            self.disconnect(client)

    async def broadcast_ticket_event(
        self,
        event_type: str,
        ticket_id: str,
        requester_id: str,
        is_internal: bool = False,
        payload: Optional[dict[str, Any]] = None,
    ) -> None:
        dsn = _pg_dsn_from_sqlalchemy_url(get_settings().DATABASE_URL)
        if dsn is None:
            await self.broadcast_local(event_type, ticket_id, requester_id, is_internal, payload)
            return

        safe_payload = dict(payload or {})
        envelope = {
            "event_type": event_type,
            "ticket_id": str(ticket_id),
            "requester_id": str(requester_id),
            "is_internal": bool(is_internal),
            "payload": safe_payload,
        }
        raw_json = json.dumps(envelope, ensure_ascii=False)
        if len(raw_json.encode("utf-8")) > MAX_PG_NOTIFY_BYTES and "summary" in safe_payload:
            safe_payload["summary"] = f"{str(safe_payload['summary'])[:200]}..."
            envelope["payload"] = safe_payload
            raw_json = json.dumps(envelope, ensure_ascii=False)

        try:
            async with AsyncSessionLocal() as session:
                await session.execute(
                    text("SELECT pg_notify(:channel, :payload)"),
                    {"channel": WS_NOTIFY_CHANNEL, "payload": raw_json},
                )
                await session.commit()
            if not self._pg_listen_enabled:
                await self.broadcast_local(event_type, ticket_id, requester_id, is_internal, safe_payload)
        except Exception as exc:
            logger.warning("PG NOTIFY broadcast failed, falling back to local broadcast: %s", exc)
            await self.broadcast_local(event_type, ticket_id, requester_id, is_internal, safe_payload)


ws_manager = ConnectionManager()
