"""
CUPS integration via pycups.
All blocking pycups calls are run in a thread pool to keep the event loop free.
"""

import asyncio

from app.config import settings

try:
    import cups

    _CUPS_AVAILABLE = True
except ImportError:
    # pycups is Linux-only; allows the app to start on dev machines without CUPS
    _CUPS_AVAILABLE = False


# CUPS job-state codes (RFC 2911)
_STATE_PENDING = {3, 4}  # pending / pending-held
_STATE_PROCESSING = {5, 6}  # processing / processing-stopped
_STATE_DONE = {9}  # completed
_STATE_FAILED = {7, 8}  # canceled / aborted


def _build_cups_options(options: dict) -> dict[str, str]:
    """Map our option schema to CUPS IPP option strings."""
    cups_opts: dict[str, str] = {}

    copies = options.get("copies", 1)
    cups_opts["copies"] = str(copies)

    paper_size = options.get("paper_size", "A4")
    cups_opts["media"] = paper_size

    # Color model - only set Gray explicitly; let printer default handle color
    if not options.get("color", True):
        cups_opts["ColorModel"] = "Gray"

    return cups_opts


def _submit_sync(file_path: str, printer_name: str, options: dict) -> int:
    if not _CUPS_AVAILABLE:
        raise RuntimeError("pycups is not installed - cannot print")
    conn = cups.Connection()
    return conn.printFile(
        printer_name,
        file_path,
        "PrintProject",
        _build_cups_options(options),
    )


def _poll_state_sync(cups_job_id: int) -> str:
    conn = cups.Connection()
    attrs = conn.getJobAttributes(cups_job_id, requested_attributes=["job-state"])
    state = attrs.get("job-state", 0)
    if state in _STATE_DONE:
        return "DONE"
    if state in _STATE_FAILED:
        return "FAILED"
    return "PRINTING"


def _get_all_printer_states_sync() -> dict[str, str]:
    if not _CUPS_AVAILABLE:
        result = {settings.document_printer_name: "offline"}
        if settings.photo_printer_name:
            result[settings.photo_printer_name] = "offline"
        return result

    conn = cups.Connection()
    printers = conn.getPrinters()
    result: dict[str, str] = {}
    configured_printers = [settings.document_printer_name]
    if settings.photo_printer_name:
        configured_printers.append(settings.photo_printer_name)

    for name in configured_printers:
        info = printers.get(name)
        if info is None:
            result[name] = "offline"
        else:
            state = info.get("printer-state", 0)
            result[name] = {3: "idle", 4: "printing", 5: "offline"}.get(state, "unknown")

    return result


async def submit_to_cups(file_path: str, printer_name: str, options: dict) -> int:
    """Submit a print job; returns the CUPS job ID."""
    return await asyncio.to_thread(_submit_sync, file_path, printer_name, options)


async def wait_for_cups_job(cups_job_id: int, poll_interval: float = 3.0) -> str:
    """Poll until the CUPS job reaches a terminal state. Returns 'DONE' or 'FAILED'."""
    while True:
        state = await asyncio.to_thread(_poll_state_sync, cups_job_id)
        if state in ("DONE", "FAILED"):
            return state
        await asyncio.sleep(poll_interval)


async def get_printer_states() -> dict[str, str]:
    """Return a dict of printer_name -> 'idle' | 'printing' | 'offline'."""
    return await asyncio.to_thread(_get_all_printer_states_sync)
