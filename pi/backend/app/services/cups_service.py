"""
CUPS integration via pycups.
All blocking pycups calls are run in a thread pool to keep the event loop free.
"""

import asyncio
import logging
import time

from app.config import settings

try:
    import cups

    _CUPS_AVAILABLE = True
except ImportError:
    # pycups is Linux-only; allows the app to start on dev machines without CUPS
    _CUPS_AVAILABLE = False


logger = logging.getLogger(__name__)


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


def _extract_job_metrics(attrs: dict) -> dict:
    pages_expected = _as_int(attrs.get("job-impressions"))
    pages_printed = _as_int(attrs.get("job-impressions-completed"))
    sheets_expected = _as_int(attrs.get("job-media-sheets"))
    sheets_printed = _as_int(attrs.get("job-media-sheets-completed"))

    # Prefer sheet counters over page counters. The kiosk contract cares about
    # physical paper output, and some drivers report page completion before a
    # sheet actually exits the printer.
    if sheets_expected is not None and sheets_printed is not None and sheets_expected > 0:
        all_pages_printed = sheets_printed >= sheets_expected
        completion_verified = True
        completion_source = "sheets"
    elif pages_expected is not None and pages_printed is not None and pages_expected > 0:
        all_pages_printed = pages_printed >= pages_expected
        completion_verified = True
        completion_source = "pages"
    else:
        # Strict rule: only treat the job as fully printed when CUPS gives us
        # explicit completion counters we can compare.
        all_pages_printed = False
        completion_verified = False
        completion_source = None

    return {
        "pagesExpected": pages_expected,
        "pagesPrinted": pages_printed,
        "sheetsExpected": sheets_expected,
        "sheetsPrinted": sheets_printed,
        "allPagesPrinted": all_pages_printed,
        "completionVerified": completion_verified,
        "completionSource": completion_source,
    }


def _summarize_result(result: dict) -> dict:
    metrics = result.get("metrics") or {}
    return {
        "status": result.get("status"),
        "message": result.get("message"),
        "reasons": result.get("reasons") or [],
        "pagesExpected": metrics.get("pagesExpected"),
        "pagesPrinted": metrics.get("pagesPrinted"),
        "sheetsExpected": metrics.get("sheetsExpected"),
        "sheetsPrinted": metrics.get("sheetsPrinted"),
        "allPagesPrinted": metrics.get("allPagesPrinted"),
        "completionVerified": metrics.get("completionVerified"),
        "completionSource": metrics.get("completionSource"),
    }


def _has_terminal_failure_signal(reasons: list[str], message: str | None) -> bool:
    text = f"{' '.join(reasons)} {message or ''}".lower()
    failure_needles = (
        "abort",
        "cancel",
        "stopped",
        "stop",
        "hold",
        "jam",
        "media-empty",
        "paper-out",
        "paper-empty",
        "media-needed",
        "door-open",
        "cover-open",
        "cartridge-missing",
        "marker-missing",
        "marker-empty",
        "toner-empty",
        "ink-empty",
        "offline",
        "filter-failed",
        "backend-failed",
        "unable",
        "error",
    )
    return any(needle in text for needle in failure_needles)


def _printer_detail_sync(printer_name: str) -> dict:
    if not _CUPS_AVAILABLE:
        return _build_offline_detail(printer_name)
    conn = cups.Connection()
    printers = conn.getPrinters()
    return _build_printer_detail_sync(conn, printers, printer_name)


def _printer_looks_healthy_for_completion(detail: dict) -> bool:
    return (
        detail.get("connection_state") == "ONLINE"
        and detail.get("operational_state") in {"IDLE", "PRINTING"}
        and detail.get("paper_out") is not True
        and detail.get("door_open") is not True
        and detail.get("cartridge_missing") is not True
        and detail.get("jammed") is not True
        and str(detail.get("ink_state") or "UNKNOWN").upper() != "EMPTY"
    )


def _printer_has_completion_red_flag(detail: dict) -> bool:
    return (
        detail.get("paper_out") is True
        or detail.get("door_open") is True
        or detail.get("cartridge_missing") is True
        or detail.get("jammed") is True
        or str(detail.get("ink_state") or "UNKNOWN").upper() == "EMPTY"
        or detail.get("operational_state") == "ERROR"
    )


def _printer_requires_attention(detail: dict) -> bool:
    return _printer_has_completion_red_flag(detail) or detail.get("connection_state") == "OFFLINE"


def _printer_red_flag_reasons(detail: dict) -> list[str]:
    reasons: list[str] = []
    if detail.get("paper_out") is True:
        reasons.append("paper-out")
    if detail.get("door_open") is True:
        reasons.append("door-open")
    if detail.get("cartridge_missing") is True:
        reasons.append("cartridge-missing")
    if detail.get("jammed") is True:
        reasons.append("jam")
    if str(detail.get("ink_state") or "UNKNOWN").upper() == "EMPTY":
        reasons.append("ink-empty")
    if detail.get("operational_state") == "ERROR":
        reasons.append("printer-error")
    if detail.get("connection_state") == "OFFLINE":
        reasons.append("printer-offline")
    return reasons


def _printer_attention_message(detail: dict) -> str:
    if detail.get("paper_out") is True:
        return "Printer is out of paper."
    if detail.get("door_open") is True:
        return "Printer cover is open."
    if detail.get("cartridge_missing") is True:
        return "Printer cartridge is missing."
    if detail.get("jammed") is True:
        return "Printer has a paper jam."
    if str(detail.get("ink_state") or "UNKNOWN").upper() == "EMPTY":
        return "Printer is out of ink."
    if detail.get("connection_state") == "OFFLINE":
        return "Printer is offline."
    if detail.get("operational_state") == "ERROR":
        return str(detail.get("message") or "Printer needs attention.")
    return "Printer is not ready."


def _printer_attention_failure_code(detail: dict) -> str:
    if detail.get("paper_out") is True:
        return "PAPER_OUT"
    if detail.get("door_open") is True:
        return "DOOR_OPEN"
    if detail.get("cartridge_missing") is True:
        return "CARTRIDGE_MISSING"
    if detail.get("jammed") is True:
        return "PAPER_JAM"
    if str(detail.get("ink_state") or "UNKNOWN").upper() == "EMPTY":
        return "INK_EMPTY"
    return "PRINT_FAILED"


def _build_printer_attention_failure(
    detail: dict,
    metrics: dict,
    reasons: list[str] | None = None,
    message: str | None = None,
) -> dict:
    failure_reasons = _dedupe_preserve_order((reasons or []) + _printer_red_flag_reasons(detail))
    return {
        "status": "FAILED",
        "message": message or _printer_attention_message(detail),
        "reasons": failure_reasons or ["printer-error"],
        "metrics": metrics,
    }


def _build_unverified_completion_failure(
    metrics: dict,
    reasons: list[str] | None = None,
    message: str | None = None,
) -> dict:
    return {
        "status": "FAILED",
        "message": message or "CUPS reported completion but full-page completion could not be verified.",
        "reasons": _dedupe_preserve_order(list(reasons or []) + ["completion-unverified"]),
        "metrics": metrics,
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


def _poll_state_sync(cups_job_id: int, printer_name: str | None = None) -> dict:
    if not _CUPS_AVAILABLE:
        raise RuntimeError("CUPS Python bindings are unavailable.")
    conn = cups.Connection()
    try:
        attrs = conn.getJobAttributes(
            cups_job_id,
            requested_attributes=_JOB_ATTRIBUTES,
        )
    except Exception as exc:
        # Never assume success when the job disappears from CUPS history. If we
        # cannot verify the final page counters, keep the OTP reusable.
        if "not-found" in str(exc).lower():
            result = {
                "status": "FAILED",
                "message": "CUPS job disappeared before full print completion could be verified.",
                "reasons": ["job-not-found", "completion-unverified"],
                "metrics": _extract_job_metrics({}),
            }
            logger.warning("CUPS job %s lookup returned not-found: %s", cups_job_id, _summarize_result(result))
            return result
        raise

    state = attrs.get("job-state", 0)
    reasons = _as_string_list(attrs.get("job-state-reasons"))
    message = attrs.get("job-state-message") or None
    metrics = _extract_job_metrics(attrs)

    if state in _STATE_BLOCKED:
        if printer_name:
            printer_detail = _printer_detail_sync(printer_name)
            if _printer_has_completion_red_flag(printer_detail):
                result = _build_printer_attention_failure(
                    printer_detail,
                    metrics,
                    reasons=reasons,
                    message=str(message or _printer_attention_message(printer_detail)),
                )
                logger.warning(
                    "CUPS job %s entered blocked state with printer red flags printer=%s detail=%s result=%s",
                    cups_job_id,
                    printer_name,
                    printer_detail,
                    _summarize_result(result),
                )
                return result
        result = {
            "status": "BLOCKED",
            "message": str(message or "job held/stopped"),
            "reasons": reasons or ["unknown"],
            "metrics": metrics,
        }
        logger.warning("CUPS job %s entered blocked state: %s", cups_job_id, _summarize_result(result))
        return result
    if state in _STATE_DONE:
        if not metrics["completionVerified"]:
            if _has_terminal_failure_signal(reasons, message):
                result = {
                    "status": "FAILED",
                    "message": "CUPS reported completion with failure indicators.",
                    "reasons": _dedupe_preserve_order(reasons + ["completion-unverified"]),
                    "metrics": metrics,
                }
                logger.warning("CUPS job %s reported done with explicit failure signals: %s", cups_job_id, _summarize_result(result))
                return result

            if printer_name:
                printer_detail = _printer_detail_sync(printer_name)
                if _printer_looks_healthy_for_completion(printer_detail):
                    result = {
                        "status": "DONE",
                        "message": str(message or "job completed"),
                        "reasons": _dedupe_preserve_order(reasons + ["completion-inferred-from-printer-state"]),
                        "metrics": metrics,
                    }
                    logger.info(
                        "CUPS job %s accepted via healthy printer-state fallback printer=%s detail=%s result=%s",
                        cups_job_id,
                        printer_name,
                        printer_detail,
                        _summarize_result(result),
                    )
                    return result

                if _printer_requires_attention(printer_detail):
                    red_flag_reasons = _printer_red_flag_reasons(printer_detail)
                    result = {
                        "status": "FAILED",
                        "message": "CUPS reported completion but printer state still showed a hardware problem.",
                        "reasons": _dedupe_preserve_order(reasons + red_flag_reasons + ["completion-unverified", "printer-red-flag"]),
                        "metrics": metrics,
                    }
                    logger.warning(
                        "CUPS job %s reported done without counters and printer red flags printer=%s detail=%s result=%s",
                        cups_job_id,
                        printer_name,
                        printer_detail,
                        _summarize_result(result),
                    )
                    return result

            result = {
                "status": "FAILED",
                "message": "CUPS reported completion but full-page completion could not be verified.",
                "reasons": _dedupe_preserve_order(reasons + ["completion-unverified"]),
                "metrics": metrics,
            }
            logger.warning(
                "CUPS job %s reported done without verifiable completion: %s",
                cups_job_id,
                _summarize_result(result),
            )
            return result
        if not metrics["allPagesPrinted"]:
            result = {
                "status": "FAILED",
                "message": "CUPS marked the job complete before all pages were printed.",
                "reasons": _dedupe_preserve_order(reasons + ["partial-print"]),
                "metrics": metrics,
            }
            logger.warning("CUPS job %s reported partial completion: %s", cups_job_id, _summarize_result(result))
            return result
        result = {
            "status": "DONE",
            "message": str(message or "job completed"),
            "reasons": reasons,
            "metrics": metrics,
        }
        logger.info("CUPS job %s reached verified completion: %s", cups_job_id, _summarize_result(result))
        return result
    if state in _STATE_FAILED:
        result = {
            "status": "FAILED",
            "message": str(message or "job failed"),
            "reasons": reasons or ["unknown"],
            "metrics": metrics,
        }
        logger.warning("CUPS job %s reported failure state: %s", cups_job_id, _summarize_result(result))
        return result
    if state in _STATE_PENDING or state in _STATE_PROCESSING:
        if printer_name:
            printer_detail = _printer_detail_sync(printer_name)
            if _printer_requires_attention(printer_detail):
                result = _build_printer_attention_failure(
                    printer_detail,
                    metrics,
                    reasons=reasons,
                )
                logger.warning(
                    "CUPS job %s remained non-terminal with printer red flags printer=%s detail=%s result=%s",
                    cups_job_id,
                    printer_name,
                    printer_detail,
                    _summarize_result(result),
                )
                return result
        return {
            "status": "PRINTING",
            "message": str(message or "job in progress"),
            "reasons": reasons,
            "metrics": metrics,
        }
    if state == 0:
        # Unknown state; keep polling for a short while before timeout.
        if printer_name:
            printer_detail = _printer_detail_sync(printer_name)
            if _printer_requires_attention(printer_detail):
                result = _build_printer_attention_failure(
                    printer_detail,
                    metrics,
                    reasons=reasons,
                )
                logger.warning(
                    "CUPS job %s entered unknown state with printer red flags printer=%s detail=%s result=%s",
                    cups_job_id,
                    printer_name,
                    printer_detail,
                    _summarize_result(result),
                )
                return result
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


async def _confirm_inferred_completion(
    cups_job_id: int,
    printer_name: str,
    result: dict,
    *,
    settle_seconds: float = 12.0,
    poll_interval: float = 2.0,
) -> dict:
    """Wait briefly after inferred completion so delayed paper-out/jam signals win."""
    metrics = result.get("metrics") or {}
    reasons = list(result.get("reasons") or [])
    deadline = time.monotonic() + settle_seconds
    saw_healthy_detail = False

    while time.monotonic() < deadline:
        printer_detail = await get_printer_detail(printer_name)

        if _printer_requires_attention(printer_detail):
            failure = _build_printer_attention_failure(
                printer_detail,
                metrics,
                reasons=reasons + ["completion-unverified", "completion-settle-failed"],
                message="Printer reported a hardware problem before output was confirmed.",
            )
            logger.warning(
                "CUPS job %s inferred completion was rejected during settle window printer=%s detail=%s result=%s",
                cups_job_id,
                printer_name,
                printer_detail,
                _summarize_result(failure),
            )
            return failure

        if _printer_looks_healthy_for_completion(printer_detail):
            saw_healthy_detail = True

        await asyncio.sleep(poll_interval)

    if not saw_healthy_detail:
        failure = _build_unverified_completion_failure(
            metrics,
            reasons=reasons + ["completion-settle-timeout"],
        )
        logger.warning(
            "CUPS job %s inferred completion timed out without stable healthy printer state: %s",
            cups_job_id,
            _summarize_result(failure),
        )
        return failure

    confirmed = {
        **result,
        "reasons": _dedupe_preserve_order(reasons + ["completion-confirmed-after-settle-window"]),
    }
    logger.info(
        "CUPS job %s inferred completion confirmed after settle window: %s",
        cups_job_id,
        _summarize_result(confirmed),
    )
    return confirmed


async def wait_for_cups_job(
    cups_job_id: int,
    printer_name: str | None = None,
    poll_interval: float = 2.0,
    timeout_seconds: int = 300,
) -> dict:
    """Poll until the CUPS job reaches a terminal state."""
    started = time.monotonic()
    last_snapshot: tuple | None = None
    while True:
        if time.monotonic() - started > timeout_seconds:
            result = {
                "status": "FAILED",
                "message": f"CUPS job {cups_job_id} timed out after {timeout_seconds}s",
                "reasons": ["timeout"],
                "metrics": {
                    "pagesExpected": None,
                    "pagesPrinted": None,
                    "sheetsExpected": None,
                    "sheetsPrinted": None,
                    "allPagesPrinted": False,
                    "completionVerified": False,
                },
            }
            logger.warning("CUPS job %s timed out: %s", cups_job_id, _summarize_result(result))
            return result

        result = await asyncio.to_thread(_poll_state_sync, cups_job_id, printer_name)
        snapshot = (
            result.get("status"),
            tuple(result.get("reasons") or []),
            result.get("message"),
            (result.get("metrics") or {}).get("pagesExpected"),
            (result.get("metrics") or {}).get("pagesPrinted"),
            (result.get("metrics") or {}).get("sheetsExpected"),
            (result.get("metrics") or {}).get("sheetsPrinted"),
            (result.get("metrics") or {}).get("allPagesPrinted"),
            (result.get("metrics") or {}).get("completionVerified"),
        )
        if snapshot != last_snapshot:
            logger.info("CUPS job %s poll update: %s", cups_job_id, _summarize_result(result))
            last_snapshot = snapshot

        if result["status"] in {"DONE", "FAILED", "BLOCKED"}:
            if result["status"] == "BLOCKED":
                result["status"] = "FAILED"
                result["message"] = str(result.get("message") or "Printer stopped before the full document finished.")
                logger.warning("CUPS job %s treated blocked state as retryable failure: %s", cups_job_id, _summarize_result(result))
            elif result["status"] == "DONE" and printer_name:
                metrics = result.get("metrics") or {}
                completion_source = metrics.get("completionSource")
                if completion_source != "sheets":
                    result = await _confirm_inferred_completion(cups_job_id, printer_name, result)
            return result
        await asyncio.sleep(poll_interval)


async def get_printer_states() -> dict[str, str]:
    """Return a dict of printer_name -> 'idle' | 'printing' | 'offline'."""
    return await asyncio.to_thread(_get_all_printer_states_sync)


async def get_printer_details() -> dict[str, dict]:
    """Return detailed printer health for each configured printer."""
    return await asyncio.to_thread(_get_all_printer_details_sync)


async def get_printer_detail(printer_name: str) -> dict:
    return await asyncio.to_thread(_printer_detail_sync, printer_name)


async def get_printer_blocking_status(printer_name: str) -> dict | None:
    detail = await get_printer_detail(printer_name)
    if not _printer_requires_attention(detail):
        return None

    return {
        "failureCode": _printer_attention_failure_code(detail),
        "failureMessage": _printer_attention_message(detail),
        "detail": detail,
    }


async def get_printer_blocking_issue(printer_name: str) -> str | None:
    blocking = await get_printer_blocking_status(printer_name)
    return None if blocking is None else str(blocking["failureMessage"])
