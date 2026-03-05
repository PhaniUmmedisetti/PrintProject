"""
CUPS integration via pycups.
All blocking pycups calls are run in a thread pool to keep the event loop free.
"""

import asyncio
import time

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
_STATE_BLOCKED = {4, 6}  # pending-held / processing-stopped


def _build_cups_options(options: dict) -> dict[str, str]:
    """Map our option schema to conservative CUPS options for max compatibility."""
    cups_opts: dict[str, str] = {}

    copies = options.get("copies", 1)
    cups_opts["copies"] = str(copies)
    # Do not force media/color options here. Many consumer printer drivers reject
    # unsupported IPP options and hold jobs as "completed-with-errors".
    # Let queue default options control paper + color mode.

    return cups_opts


def _prepare_printer_sync(printer_name: str) -> None:
    if not _CUPS_AVAILABLE:
        return
    conn = cups.Connection()
    try:
        conn.enablePrinter(printer_name)
    except Exception:
        pass
    try:
        conn.acceptJobs(printer_name)
    except Exception:
        pass


def _submit_sync(file_path: str, printer_name: str, options: dict) -> int:
    if not _CUPS_AVAILABLE:
        raise RuntimeError(
            "CUPS Python bindings are unavailable. Install OS package 'python3-cups' "
            "and recreate venv with --system-site-packages."
        )
    conn = cups.Connection()
    available = sorted(conn.getPrinters().keys())
    if printer_name not in available:
        raise RuntimeError(
            f"Configured printer '{printer_name}' was not found in CUPS. Available: {', '.join(available)}"
        )
    _prepare_printer_sync(printer_name)
    return conn.printFile(
        printer_name,
        file_path,
        "PrintProject",
        _build_cups_options(options),
    )


def _poll_state_sync(cups_job_id: int) -> str:
    if not _CUPS_AVAILABLE:
        raise RuntimeError("CUPS Python bindings are unavailable.")
    conn = cups.Connection()
    try:
        attrs = conn.getJobAttributes(
            cups_job_id,
            requested_attributes=["job-state", "job-state-reasons", "job-state-message"],
        )
    except Exception as exc:
        # Some CUPS setups purge completed jobs quickly and then return not-found.
        # Treat that as completed to avoid false negatives after successful print.
        if "not-found" in str(exc).lower():
            return "DONE"
        raise

    state = attrs.get("job-state", 0)
    if state in _STATE_BLOCKED:
        reasons = attrs.get("job-state-reasons") or "unknown"
        message = attrs.get("job-state-message") or "job held/stopped"
        raise RuntimeError(f"CUPS job blocked: {message} ({reasons})")
    if state in _STATE_DONE:
        return "DONE"
    if state in _STATE_FAILED:
        reasons = attrs.get("job-state-reasons") or "unknown"
        message = attrs.get("job-state-message") or "job failed"
        raise RuntimeError(f"CUPS job failed: {message} ({reasons})")
    if state in _STATE_PENDING or state in _STATE_PROCESSING:
        return "PRINTING"
    if state == 0:
        # Unknown state; keep polling for a short while before timeout.
        return "PRINTING"
    return "PRINTING"


def _restart_job_sync(cups_job_id: int) -> None:
    if not _CUPS_AVAILABLE:
        return
    conn = cups.Connection()
    conn.restartJob(cups_job_id)


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


async def wait_for_cups_job(
    cups_job_id: int,
    poll_interval: float = 2.0,
    timeout_seconds: int = 300,
) -> str:
    """Poll until the CUPS job reaches a terminal state. Returns 'DONE' or 'FAILED'."""
    started = time.monotonic()
    restarted_once = False
    while True:
        if time.monotonic() - started > timeout_seconds:
            raise TimeoutError(f"CUPS job {cups_job_id} timed out after {timeout_seconds}s")

        try:
            state = await asyncio.to_thread(_poll_state_sync, cups_job_id)
        except RuntimeError as exc:
            text = str(exc).lower()
            if "blocked" in text and not restarted_once:
                await asyncio.to_thread(_restart_job_sync, cups_job_id)
                restarted_once = True
                await asyncio.sleep(2)
                continue
            raise

        if state == "DONE":
            return "DONE"
        if state == "FAILED":
            return state
        await asyncio.sleep(poll_interval)


async def get_printer_states() -> dict[str, str]:
    """Return a dict of printer_name -> 'idle' | 'printing' | 'offline'."""
    return await asyncio.to_thread(_get_all_printer_states_sync)
