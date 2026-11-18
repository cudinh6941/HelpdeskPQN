import asyncio
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal, Base, engine
from app.core.minio_client import storage_service
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

    storage_service.ensure_bucket()

    async with AsyncSessionLocal() as db:
        await seed_initial_data(db)

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
