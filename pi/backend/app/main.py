import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import get_in_flight_jobs, init_db, set_terminal_event, update_job
from app.routers import print_jobs
from app.tasks.cloud_sync import cloud_sync_loop, sync_terminal_event_payload
from app.tasks.heartbeat import heartbeat_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("Database initialised")

    in_flight = await get_in_flight_jobs()
    if in_flight:
        logger.warning("Found %d in-flight jobs from before restart - marking FAILED", len(in_flight))
        for job in in_flight:
            await update_job(
                job["id"],
                "FAILED",
                error_msg="Pi restarted mid-job",
                failure_code="AGENT_RESTARTED",
                retryable=True,
            )
            payload = {
                "jobId": job["id"],
                "cupsJobId": job.get("cups_job_id"),
                "failureCode": "AGENT_RESTARTED",
                "failureMessage": "Pi restarted mid-job",
                "isRetryable": True,
            }
            await set_terminal_event(job["id"], "FAILED", payload)
            try:
                await sync_terminal_event_payload(job["id"], "FAILED", payload)
            except Exception as exc:
                logger.warning("Could not notify backend for job %s: %s", job["id"], exc)

    hb_task = asyncio.create_task(heartbeat_loop())
    cloud_sync_task = asyncio.create_task(cloud_sync_loop())
    logger.info("Background tasks started")

    yield

    hb_task.cancel()
    cloud_sync_task.cancel()
    try:
        await hb_task
    except asyncio.CancelledError:
        pass
    try:
        await cloud_sync_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="PrintNest Kiosk Agent",
    description="Local kiosk agent running on Raspberry Pi - talks to PrintNest device APIs and controls CUPS.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173"],
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["*"],
)

app.include_router(print_jobs.router)


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok"}
