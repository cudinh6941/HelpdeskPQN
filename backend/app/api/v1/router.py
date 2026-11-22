from fastapi import APIRouter

from app.api.v1 import admin, analytics, attachments, auth, comments, kb, macros, notifications, tickets, ws

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(auth.router)
api_v1_router.include_router(tickets.router)
api_v1_router.include_router(comments.router)
api_v1_router.include_router(attachments.router)
api_v1_router.include_router(kb.router)
api_v1_router.include_router(macros.router)
api_v1_router.include_router(notifications.router)
api_v1_router.include_router(admin.router)
api_v1_router.include_router(analytics.router)
api_v1_router.include_router(ws.router)
