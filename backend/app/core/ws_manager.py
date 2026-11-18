from dataclasses import dataclass
import logging
from typing import Any, Optional

from fastapi import WebSocket

from app.models.models import UserRole

logger = logging.getLogger(__name__)

IT_WS_ROLES = {UserRole.IT_AGENT, UserRole.IT_LEAD, UserRole.SYS_ADMIN}


@dataclass(eq=False)
class _WsClient:
    websocket: WebSocket
    user_id: str
    role: UserRole


class ConnectionManager:
    """In-memory WebSocket connection hub with per-role RBAC event filtering."""

    def __init__(self) -> None:
        self._clients: set[_WsClient] = set()

    async def connect(self, websocket: WebSocket, user_id: str, role: UserRole) -> _WsClient:
        await websocket.accept()
        client = _WsClient(websocket=websocket, user_id=user_id, role=role)
        self._clients.add(client)
        return client

    def disconnect(self, client: _WsClient) -> None:
        self._clients.discard(client)

    async def broadcast_ticket_event(
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


ws_manager = ConnectionManager()
