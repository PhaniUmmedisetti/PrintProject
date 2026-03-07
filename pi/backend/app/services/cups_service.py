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
_PRINTER_ATTRIBUTES = [
    "printer-state",
    "printer-state-reasons",
    "printer-state-message",
    "printer-alert",
    "printer-alert-description",
    "marker-message",
    "marker-names",
    "marker-types",
    "marker-levels",
    "marker-low-levels",
    "marker-high-levels",
    "marker-states",
]
_JOB_ATTRIBUTES = [
    "job-state",
    "job-state-reasons",
    "job-state-message",
    "job-impressions",
    "job-impressions-completed",
    "job-media-sheets",
    "job-media-sheets-completed",
]


def _build_cups_options(options: dict) -> dict[str, str]:
    """Map our option schema to conservative CUPS options for max compatibility."""
    cups_opts: dict[str, str] = {}

    copies = options.get("copies", 1)
    cups_opts["copies"] = str(copies)
    # Do not force media/color options here. Many consumer printer drivers reject
    # unsupported IPP options and hold jobs as "completed-with-errors".
    # Let queue default options control paper + color mode.

    return cups_opts


def _state_label(state: int) -> str:
    return {3: "idle", 4: "printing", 5: "offline"}.get(state, "unknown")


def _as_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _has_reason(reasons: list[str], *needles: str) -> bool:
    lowered_needles = tuple(needle.lower() for needle in needles)
    for reason in reasons:
        text = reason.lower()
        if any(needle in text for needle in lowered_needles):
            return True
    return False


def _detect_ink_state(reasons: list[str]) -> str:
    if _has_reason(
        reasons,
        "marker-supply-empty",
        "marker-empty",
        "toner-empty",
        "ink-empty",
    ):
        return "EMPTY"
    if _has_reason(
        reasons,
        "marker-supply-low",
        "marker-low",
        "toner-low",
        "ink-low",
    ):
        return "LOW"
    if _has_reason(
        reasons,
        "marker-supply-ok",
        "marker-ok",
        "toner-ok",
        "ink-ok",
    ):
        return "OK"
    return "UNKNOWN"


def _build_offline_detail(printer_name: str) -> dict:
    return {
        "printer_name": printer_name,
        "state": "offline",
        "connection_state": "OFFLINE",
        "operational_state": "STOPPED",
        "paper_out": None,
        "door_open": None,
        "cartridge_missing": None,
        "jammed": None,
        "ink_state": "UNKNOWN",
        "message": "Printer not found in CUPS",
        "reasons": ["printer-not-configured"],
    }


def _as_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_job_metrics(attrs: dict, *, assume_complete: bool) -> dict:
    pages_expected = _as_int(attrs.get("job-impressions"))
    pages_printed = _as_int(attrs.get("job-impressions-completed"))
    sheets_expected = _as_int(attrs.get("job-media-sheets"))
    sheets_printed = _as_int(attrs.get("job-media-sheets-completed"))

    if pages_expected is not None and pages_printed is not None:
        all_pages_printed = pages_printed >= pages_expected
    elif sheets_expected is not None and sheets_printed is not None:
        all_pages_printed = sheets_printed >= sheets_expected
    else:
        all_pages_printed = assume_complete

    return {
        "pagesExpected": pages_expected,
        "pagesPrinted": pages_printed,
        "sheetsExpected": sheets_expected,
        "sheetsPrinted": sheets_printed,
        "allPagesPrinted": all_pages_printed,
    }


def _build_printer_detail_sync(conn: "cups.Connection", printers: dict, printer_name: str) -> dict:
    info = printers.get(printer_name)
    if info is None:
        return _build_offline_detail(printer_name)

    try:
        attrs = conn.getPrinterAttributes(printer_name, requested_attributes=_PRINTER_ATTRIBUTES)
    except Exception:
        attrs = {}

    state_code = int(attrs.get("printer-state", info.get("printer-state", 0)) or 0)
    state = _state_label(state_code)

    reasons = _dedupe_preserve_order(
        _as_string_list(attrs.get("printer-state-reasons"))
        + _as_string_list(attrs.get("printer-alert"))
        + _as_string_list(attrs.get("printer-alert-description"))
        + _as_string_list(attrs.get("marker-message"))
        + _as_string_list(attrs.get("marker-states"))
    )
    message = str(attrs.get("printer-state-message") or info.get("printer-state-message") or "").strip() or None

    known_online = state in {"idle", "printing"}
    paper_out = (
        True
        if _has_reason(reasons, "media-empty", "paper-out", "paper-empty", "media-needed")
        else False if known_online
        else None
    )
    door_open = True if _has_reason(reasons, "door-open", "cover-open") else False if known_online else None
    cartridge_missing = (
        True if _has_reason(reasons, "cartridge-missing", "marker-missing") else False if known_online else None
    )
    jammed = True if _has_reason(reasons, "jam", "jammed") else False if known_online else None
    ink_state = _detect_ink_state(reasons)

    if state == "printing":
        connection_state = "ONLINE"
        operational_state = "PRINTING"
    elif state == "offline":
        connection_state = "OFFLINE"
        operational_state = "STOPPED"
    elif any(flag is True for flag in (paper_out, door_open, cartridge_missing, jammed)) or ink_state in {"LOW", "EMPTY"}:
        connection_state = "ONLINE"
        operational_state = "ERROR"
    elif state == "idle":
        connection_state = "ONLINE"
        operational_state = "IDLE"
    else:
        connection_state = "UNKNOWN"
        operational_state = "UNKNOWN"

    return {
        "printer_name": printer_name,
        "state": state,
        "connection_state": connection_state,
        "operational_state": operational_state,
        "paper_out": paper_out,
        "door_open": door_open,
        "cartridge_missing": cartridge_missing,
        "jammed": jammed,
        "ink_state": ink_state,
        "message": message,
        "reasons": reasons,
    }


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


def _poll_state_sync(cups_job_id: int) -> dict:
    if not _CUPS_AVAILABLE:
        raise RuntimeError("CUPS Python bindings are unavailable.")
    conn = cups.Connection()
    try:
        attrs = conn.getJobAttributes(
            cups_job_id,
            requested_attributes=_JOB_ATTRIBUTES,
        )
    except Exception as exc:
        # Some CUPS setups purge completed jobs quickly and then return not-found.
        # Treat that as completed to avoid false negatives after successful print.
        if "not-found" in str(exc).lower():
            return {
                "status": "DONE",
                "message": "CUPS job disappeared from history; assuming complete.",
                "reasons": ["job-not-found"],
                "metrics": _extract_job_metrics({}, assume_complete=True),
            }
        raise

    state = attrs.get("job-state", 0)
    reasons = _as_string_list(attrs.get("job-state-reasons"))
    message = attrs.get("job-state-message") or None
    metrics = _extract_job_metrics(attrs, assume_complete=state in _STATE_DONE)

    if state in _STATE_BLOCKED:
        return {
            "status": "BLOCKED",
            "message": str(message or "job held/stopped"),
            "reasons": reasons or ["unknown"],
            "metrics": metrics,
        }
    if state in _STATE_DONE:
        if not metrics["allPagesPrinted"]:
            return {
                "status": "FAILED",
                "message": "CUPS marked the job complete before all pages were printed.",
                "reasons": _dedupe_preserve_order(reasons + ["partial-print"]),
                "metrics": metrics,
            }
        return {
            "status": "DONE",
            "message": str(message or "job completed"),
            "reasons": reasons,
            "metrics": metrics,
        }
    if state in _STATE_FAILED:
        return {
            "status": "FAILED",
            "message": str(message or "job failed"),
            "reasons": reasons or ["unknown"],
            "metrics": metrics,
        }
    if state in _STATE_PENDING or state in _STATE_PROCESSING:
        return {
            "status": "PRINTING",
            "message": str(message or "job in progress"),
            "reasons": reasons,
            "metrics": metrics,
        }
    if state == 0:
        # Unknown state; keep polling for a short while before timeout.
        return {
            "status": "PRINTING",
            "message": str(message or "job state unknown"),
            "reasons": reasons,
            "metrics": metrics,
        }
    return {
        "status": "PRINTING",
        "message": str(message or "job in progress"),
        "reasons": reasons,
        "metrics": metrics,
    }


def _restart_job_sync(cups_job_id: int) -> None:
    if not _CUPS_AVAILABLE:
        return
    conn = cups.Connection()
    conn.restartJob(cups_job_id)


def _get_all_printer_states_sync() -> dict[str, str]:
    return {name: detail["state"] for name, detail in _get_all_printer_details_sync().items()}


def _get_all_printer_details_sync() -> dict[str, dict]:
    configured_printers = [settings.document_printer_name]
    if settings.photo_printer_name:
        configured_printers.append(settings.photo_printer_name)

    if not _CUPS_AVAILABLE:
        return {name: _build_offline_detail(name) for name in configured_printers}

    conn = cups.Connection()
    printers = conn.getPrinters()
    return {name: _build_printer_detail_sync(conn, printers, name) for name in configured_printers}


async def submit_to_cups(file_path: str, printer_name: str, options: dict) -> int:
    """Submit a print job; returns the CUPS job ID."""
    return await asyncio.to_thread(_submit_sync, file_path, printer_name, options)


async def wait_for_cups_job(
    cups_job_id: int,
    poll_interval: float = 2.0,
    timeout_seconds: int = 300,
) -> dict:
    """Poll until the CUPS job reaches a terminal state."""
    started = time.monotonic()
    restarted_once = False
    while True:
        if time.monotonic() - started > timeout_seconds:
            return {
                "status": "FAILED",
                "message": f"CUPS job {cups_job_id} timed out after {timeout_seconds}s",
                "reasons": ["timeout"],
                "metrics": {
                    "pagesExpected": None,
                    "pagesPrinted": None,
                    "sheetsExpected": None,
                    "sheetsPrinted": None,
                    "allPagesPrinted": False,
                },
            }

        result = await asyncio.to_thread(_poll_state_sync, cups_job_id)

        if result["status"] == "BLOCKED" and not restarted_once:
            await asyncio.to_thread(_restart_job_sync, cups_job_id)
            restarted_once = True
            await asyncio.sleep(2)
            continue
        if result["status"] in {"DONE", "FAILED", "BLOCKED"}:
            if result["status"] == "BLOCKED":
                result["status"] = "FAILED"
            return result
        await asyncio.sleep(poll_interval)


async def get_printer_states() -> dict[str, str]:
    """Return a dict of printer_name -> 'idle' | 'printing' | 'offline'."""
    return await asyncio.to_thread(_get_all_printer_states_sync)


async def get_printer_details() -> dict[str, dict]:
    """Return detailed printer health for each configured printer."""
    return await asyncio.to_thread(_get_all_printer_details_sync)
