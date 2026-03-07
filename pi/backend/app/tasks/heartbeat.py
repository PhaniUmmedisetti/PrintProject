"""Background heartbeat loop for PrintNest device telemetry."""

import asyncio
import logging

from app.config import settings
from app.services.cloud_api import post_heartbeat
from app.services.cups_service import get_printer_details

logger = logging.getLogger(__name__)


async def heartbeat_loop() -> None:
    while True:
        try:
            details = await get_printer_details()
            await post_heartbeat(details)
        except Exception as exc:
            logger.warning("Heartbeat failed: %s", exc)
        await asyncio.sleep(settings.heartbeat_interval)
