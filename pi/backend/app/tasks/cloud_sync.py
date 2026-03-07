"""Retry delivery of terminal print events to PrintNest."""

import asyncio
import logging

from app.database import (
    get_unsynced_terminal_events,
    mark_terminal_event_synced,
    set_terminal_event_error,
)
from app.services.cloud_api import sync_terminal_event

logger = logging.getLogger(__name__)

SYNC_INTERVAL_SECONDS = 15


async def sync_terminal_event_payload(job_id: str, event_type: str, payload: dict) -> bool:
    try:
        await sync_terminal_event(event_type, payload)
    except Exception as exc:
        await set_terminal_event_error(job_id, str(exc))
        logger.warning("Cloud sync failed for job %s event=%s: %s", job_id, event_type, exc)
        return False

    await mark_terminal_event_synced(job_id)
    return True


async def cloud_sync_loop() -> None:
    while True:
        try:
            jobs = await get_unsynced_terminal_events()
            for job in jobs:
                payload = job.get("terminal_event_payload")
                event_type = job.get("terminal_event_type")
                if not event_type or not isinstance(payload, dict):
                    continue
                await sync_terminal_event_payload(job["id"], str(event_type), payload)
        except Exception as exc:
            logger.warning("Cloud sync loop failed: %s", exc)

        await asyncio.sleep(SYNC_INTERVAL_SECONDS)
