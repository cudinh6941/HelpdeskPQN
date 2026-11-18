import asyncio
import logging

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.workers.outbox_dispatcher import dispatch_pending_outbox_batch
from app.workers.sla_scanner import scan_sla_deadlines

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("helpdesk.worker")


async def run_outbox_loop() -> None:
    settings = get_settings()
    interval = max(2, settings.OUTBOX_POLL_INTERVAL_SECONDS)
    logger.info("Starting Outbox Dispatcher loop (interval=%ss)", interval)
    while True:
        try:
            async with AsyncSessionLocal() as db:
                await dispatch_pending_outbox_batch(db)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Outbox Dispatcher error: %s", exc)
        await asyncio.sleep(interval)


async def run_sla_scanner_loop() -> None:
    settings = get_settings()
    interval = max(5, settings.SLA_SCAN_INTERVAL_SECONDS)
    logger.info("Starting SLA Scanner loop (interval=%ss)", interval)
    while True:
        try:
            async with AsyncSessionLocal() as db:
                await scan_sla_deadlines(db)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("SLA Scanner error: %s", exc)
        await asyncio.sleep(interval)


async def main() -> None:
    await asyncio.gather(run_outbox_loop(), run_sla_scanner_loop())


if __name__ == "__main__":
    asyncio.run(main())
