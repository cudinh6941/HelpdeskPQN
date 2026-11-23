import asyncio
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal, Base, engine
from app.core.minio_client import storage_service
from app.core.ws_manager import ws_manager
import app.models  # noqa: F401
from app.seed import seed_initial_data
from app.workers.runner import run_outbox_loop, run_sla_scanner_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("helpdesk.api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()

    if settings.DATABASE_URL.startswith("sqlite"):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            cols = (await conn.execute(text("PRAGMA table_info(ticket_attachments)"))).fetchall()
            col_names = {row[1] for row in cols}
            if "kb_article_id" not in col_names:
                await conn.execute(text("ALTER TABLE ticket_attachments ADD COLUMN kb_article_id CHAR(32)"))
                await conn.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_ticket_attachments_kb_article_id ON ticket_attachments (kb_article_id)")
                )
            t_cols = (await conn.execute(text("PRAGMA table_info(tickets)"))).fetchall()
            t_col_names = {row[1] for row in t_cols}
            if "parent_ticket_id" not in t_col_names:
                await conn.execute(text("ALTER TABLE tickets ADD COLUMN parent_ticket_id CHAR(36)"))
                await conn.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_tickets_parent_ticket_id ON tickets (parent_ticket_id)")
                )
            c_cols = (await conn.execute(text("PRAGMA table_info(ticket_comments)"))).fetchall()
            c_col_names = {row[1] for row in c_cols}
            if "kb_article_id" not in c_col_names:
                await conn.execute(text("ALTER TABLE ticket_comments ADD COLUMN kb_article_id CHAR(32)"))
                await conn.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_ticket_comments_kb_article_id ON ticket_comments (kb_article_id)")
                )

    storage_service.ensure_bucket()

    async with AsyncSessionLocal() as db:
        await seed_initial_data(db)

    await ws_manager.start_pg_listener()

    worker_tasks: list[asyncio.Task] = []
    if settings.RUN_EMBEDDED_WORKERS:
        worker_tasks = [
            asyncio.create_task(run_outbox_loop()),
            asyncio.create_task(run_sla_scanner_loop()),
        ]
        logger.info("Embedded Outbox & SLA workers started.")

    try:
        yield
    finally:
        for task in worker_tasks:
            task.cancel()
        if worker_tasks:
            await asyncio.gather(*worker_tasks, return_exceptions=True)
        await ws_manager.stop_pg_listener()


settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="Internal IT Helpdesk System with LDAP Auth, SLA Engine, MinIO Paste Upload & Transactional Outbox",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "ldap_enabled": settings.LDAP_ENABLED,
        "minio_enabled": settings.MINIO_ENABLED,
    }


app.include_router(api_v1_router)
