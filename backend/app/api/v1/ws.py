from typing import Optional
import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from jose import JWTError, jwt
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.ws_manager import ws_manager
from app.models.models import User

router = APIRouter(tags=["WebSocket Real-time"])


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(default=None),
):
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        if payload.get("scope") not in (None, "ws"):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        user_uuid = uuid.UUID(payload["sub"])
    except (JWTError, KeyError, ValueError):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    async with AsyncSessionLocal() as db:
        res = await db.execute(select(User).where(User.id == user_uuid))
        user = res.scalar_one_or_none()

    if user is None or not user.is_active:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    client = await ws_manager.connect(websocket, str(user.id), user.role)
    try:
        while True:
            text = await websocket.receive_text()
            if text == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(client)
