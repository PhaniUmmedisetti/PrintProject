import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import get_in_flight_jobs, init_db, update_job
from app.routers import print_jobs
from app.services.cloud_api import mark_failed
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
            await update_job(job["id"], "FAILED", error_msg="Pi restarted mid-job")
            try:
                await mark_failed(
                    job["id"],
                    cups_job_id=job.get("cups_job_id"),
                    failure_code="AGENT_RESTARTED",
                    failure_message="Pi restarted mid-job",
                    is_retryable=False,
                )
            except Exception as exc:
                logger.warning("Could not notify backend for job %s: %s", job["id"], exc)

    hb_task = asyncio.create_task(heartbeat_loop())
    logger.info("Heartbeat started")

    yield

    hb_task.cancel()
    try:
        await hb_task
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
