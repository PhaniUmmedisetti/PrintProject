"""Thin wrapper around the PrintNest device REST API."""

import base64
import hashlib
import hmac
import json
import time
from pathlib import Path

import aiofiles
import httpx

from app.config import settings

_EMPTY_BODY_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class InvalidOtpError(Exception):
    """Raised when the provided OTP cannot be released."""


class PrinterNotReadyError(Exception):
    """Raised when the backend blocks release due to printer health."""

    def __init__(self, message: str, failure_code: str = "PRINTER_NOT_READY"):
        super().__init__(message)
        self.failure_code = failure_code


def _body_hash(body: bytes) -> str:
    if not body:
        return _EMPTY_BODY_HASH
    return hashlib.sha256(body).hexdigest()


def _build_headers(method: str, path: str, body: bytes, bearer_token: str | None = None) -> dict[str, str]:
    timestamp = str(int(time.time()))
    message = f"{timestamp}\n{method.upper()}\n{path}\n{_body_hash(body)}"
    secret_bytes = base64.b64decode(settings.shared_secret)
    signature = hmac.new(secret_bytes, message.encode("utf-8"), hashlib.sha256).hexdigest()

    headers = {
        "X-Device-Id": settings.device_id,
        "X-Timestamp": timestamp,
        "X-Signature": signature,
    }
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    return headers


async def _request(
    method: str,
    path: str,
    *,
    json_body: dict | None = None,
    bearer_token: str | None = None,
    timeout: float = 15.0,
) -> httpx.Response:
    body = b""
    headers: dict[str, str] = {}
    if json_body is not None:
        body = json.dumps(json_body, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"

    headers.update(_build_headers(method, path, body, bearer_token=bearer_token))

    async with httpx.AsyncClient(timeout=timeout) as client:
        return await client.request(
            method,
            f"{settings.cloud_api_url}{path}",
            content=body if json_body is not None else None,
            headers=headers,
        )


async def release_job(otp: str) -> dict:
    """Release a PrintNest job for this device and receive a short-lived file token."""
    payload = {"otp": otp}
    if settings.store_id:
        payload["storeId"] = settings.store_id

    response = await _request("POST", "/api/v1/device/release", json_body=payload)

    if response.status_code == 400:
        raise InvalidOtpError()

    if response.status_code == 409:
        error = response.json().get("error", {})
        error_code = error.get("code")
        if error_code == "LOCK_CONFLICT":
            raise InvalidOtpError()
        if error_code == "PRINTER_NOT_READY":
            message = error.get("message", "Printer not ready.")
            raise PrinterNotReadyError(message, failure_code="PRINTER_NOT_READY")

    response.raise_for_status()
    payload = response.json()
    return {
        "job_id": payload["jobId"],
        "job_summary": payload["jobSummary"],
        "file_token": payload["fileToken"]["token"],
    }


async def download_pdf(job_id: str, file_token: str, destination: Path) -> None:
    """Download the released PDF through the authenticated device file endpoint."""
    path = f"/api/v1/device/printjobs/{job_id}/file"
    headers = _build_headers("GET", path, b"", bearer_token=file_token)
    destination.parent.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("GET", f"{settings.cloud_api_url}{path}", headers=headers) as response:
            response.raise_for_status()
            async with aiofiles.open(destination, "wb") as output:
                async for chunk in response.aiter_bytes(chunk_size=65_536):
                    await output.write(chunk)


async def mark_printing_started(job_id: str, cups_job_id: str | None, printer_name: str) -> None:
    response = await _request(
        "POST",
        f"/api/v1/device/printjobs/{job_id}/printing-started",
        json_body={"cupsJobId": cups_job_id, "printerName": printer_name},
    )
    response.raise_for_status()


async def mark_completed(job_id: str, cups_job_id: str | None, metrics: dict | None = None) -> None:
    response = await _request(
        "POST",
        f"/api/v1/device/printjobs/{job_id}/completed",
        json_body={"cupsJobId": cups_job_id, "metrics": metrics},
    )
    response.raise_for_status()


async def mark_failed(
    job_id: str,
    cups_job_id: str | None,
    failure_code: str,
    failure_message: str,
    is_retryable: bool,
) -> None:
    response = await _request(
        "POST",
        f"/api/v1/device/printjobs/{job_id}/failed",
        json_body={
            "cupsJobId": cups_job_id,
            "failureCode": failure_code,
            "failureMessage": failure_message,
            "isRetryable": is_retryable,
        },
    )
    response.raise_for_status()


async def sync_terminal_event(event_type: str, payload: dict) -> None:
    event = event_type.upper()
    if event == "COMPLETED":
        await mark_completed(
            payload["jobId"],
            payload.get("cupsJobId"),
            metrics=payload.get("metrics"),
        )
        return
    if event == "FAILED":
        await mark_failed(
            payload["jobId"],
            payload.get("cupsJobId"),
            str(payload.get("failureCode") or "PRINT_FAILED"),
            str(payload.get("failureMessage") or "Print failed."),
            bool(payload.get("isRetryable")),
        )
        return
    raise ValueError(f"Unsupported terminal event type: {event_type}")


def _aggregate_bool(values: list[bool | None]) -> bool | None:
    if any(value is True for value in values):
        return True
    if any(value is False for value in values):
        return False
    return None


def _aggregate_ink_state(values: list[str]) -> str:
    if any(value == "EMPTY" for value in values):
        return "EMPTY"
    if any(value == "LOW" for value in values):
        return "LOW"
    if any(value == "OK" for value in values):
        return "OK"
    return "UNKNOWN"


async def post_heartbeat(printer_details: dict) -> None:
    """Send normalized printer health to the PrintNest heartbeat endpoint."""
    details = {name: detail for name, detail in printer_details.items() if name}
    states = {name: detail.get("state", "unknown") for name, detail in details.items()}
    is_printing = any(detail.get("operational_state") == "PRINTING" for detail in details.values())
    has_attention = any(detail.get("operational_state") == "ERROR" for detail in details.values())
    any_online = any(detail.get("connection_state") == "ONLINE" for detail in details.values())
    all_offline = bool(details) and all(detail.get("connection_state") == "OFFLINE" for detail in details.values())

    if is_printing:
        connection_state = "ONLINE"
        operational_state = "PRINTING"
    elif has_attention:
        connection_state = "ONLINE" if any_online else "UNKNOWN"
        operational_state = "ERROR"
    elif any_online:
        connection_state = "ONLINE"
        operational_state = "IDLE"
    elif all_offline:
        connection_state = "OFFLINE"
        operational_state = "UNKNOWN"
    else:
        connection_state = "UNKNOWN"
        operational_state = "UNKNOWN"

    printer_model = ", ".join(sorted(states.keys())) if states else None
    paper_out = _aggregate_bool([detail.get("paper_out") for detail in details.values()])
    door_open = _aggregate_bool([detail.get("door_open") for detail in details.values()])
    cartridge_missing = _aggregate_bool([detail.get("cartridge_missing") for detail in details.values()])
    ink_state = _aggregate_ink_state([str(detail.get("ink_state", "UNKNOWN")) for detail in details.values()])
    payload = {
        "storeId": settings.store_id,
        "capabilitiesJson": json.dumps({"printers": list(states.keys())}),
        "printerHealth": {
            "printerModel": printer_model,
            "connectionState": connection_state,
            "operationalState": operational_state,
            "paperOut": paper_out,
            "doorOpen": door_open,
            "cartridgeMissing": cartridge_missing,
            "inkState": ink_state,
            "rawStatusJson": json.dumps(details),
        },
    }

    response = await _request("POST", "/api/v1/device/heartbeat", json_body=payload, timeout=10.0)
    response.raise_for_status()
