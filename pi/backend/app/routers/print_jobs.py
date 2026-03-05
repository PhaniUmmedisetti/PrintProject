import json
import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.database import create_job, get_job, update_job
from app.services import cloud_api, cups_service
from app.services.converter import convert_to_pdf_if_needed
from app.services.downloader import download_file

router = APIRouter(prefix="/local", tags=["print"])
logger = logging.getLogger(__name__)


class PrintRequest(BaseModel):
    code: str


def _assert_pdf_looks_valid(file_path: Path) -> None:
    """Cheap PDF sanity checks to avoid sending corrupt files to CUPS."""
    size = file_path.stat().st_size
    if size < 32:
        raise RuntimeError(f"Downloaded file is too small to be a PDF ({size} bytes)")

    with file_path.open("rb") as fh:
        head = fh.read(8)
        fh.seek(max(size - 2048, 0))
        tail = fh.read()

    if not head.startswith(b"%PDF-"):
        preview = head.decode("utf-8", errors="replace")
        raise RuntimeError(f"Downloaded file is not a PDF (header='{preview}')")

    if b"%%EOF" not in tail:
        raise RuntimeError("Downloaded PDF is incomplete (missing EOF marker)")


def _resolve_printer_name(job_summary: dict) -> str:
    color = str(job_summary.get("color", "BW")).upper()
    if color != "BW" and settings.photo_printer_name:
        return settings.photo_printer_name
    return settings.document_printer_name


@router.post("/print")
async def start_print(request: PrintRequest, background_tasks: BackgroundTasks):
    code = request.code.strip()

    try:
        job = await cloud_api.release_job(code)
    except cloud_api.InvalidOtpError:
        raise HTTPException(status_code=404, detail="Invalid or expired code")
    except cloud_api.PrinterNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    job_id = job["job_id"]
    printer_name = _resolve_printer_name(job["job_summary"])

    await create_job(
        job_id=job_id,
        file_token=job["file_token"],
        printer_name=printer_name,
        job_summary=json.dumps(job["job_summary"]),
    )

    background_tasks.add_task(_download_and_convert, job)

    return {
        "job_id": job_id,
        "status": "DOWNLOADING",
        "job_summary": job["job_summary"],
    }


@router.post("/confirm/{job_id}")
async def confirm_print(job_id: str, background_tasks: BackgroundTasks):
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "READY":
        raise HTTPException(
            status_code=409,
            detail=f"Job is not ready for printing (status: {job['status']})",
        )

    background_tasks.add_task(
        _submit_and_monitor,
        job_id,
        job["file_path"],
        job["printer_name"],
        job["job_summary"] or {},
    )

    return {"job_id": job_id, "status": "PRINTING"}


@router.get("/status/{job_id}")
async def get_status(job_id: str):
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/printers")
async def get_printers():
    states = await cups_service.get_printer_states()
    return {"printers": states}


async def _download_and_convert(job: dict) -> None:
    job_id = job["job_id"]
    job_dir = Path(settings.temp_dir) / job_id

    try:
        file_path = await download_file(job_id=job_id, file_token=job["file_token"])
        try:
            size = file_path.stat().st_size
        except OSError:
            size = -1
        logger.info("Job %s downloaded to %s (%d bytes)", job_id, file_path, size)
        _assert_pdf_looks_valid(file_path)
        await update_job(job_id, "CONVERTING", file_path=str(file_path))

        print_path = await convert_to_pdf_if_needed(file_path, "pdf")
        logger.info("Job %s ready for print path=%s", job_id, print_path)
        await update_job(job_id, "READY", file_path=str(print_path))
    except Exception as exc:
        await update_job(job_id, "FAILED", error_msg=str(exc))
        try:
            await cloud_api.mark_failed(
                job_id,
                cups_job_id=None,
                failure_code="DOWNLOAD_FAILED",
                failure_message=str(exc),
                is_retryable=True,
            )
        except Exception:
            pass
        if job_dir.exists() and not settings.keep_failed_job_files:
            shutil.rmtree(job_dir, ignore_errors=True)
        elif job_dir.exists():
            logger.warning("Keeping failed job files for debug: %s", job_dir)


async def _submit_and_monitor(
    job_id: str,
    file_path: str,
    printer_name: str,
    job_summary: dict,
) -> None:
    job_dir = Path(settings.temp_dir) / job_id
    cups_job_id_str: str | None = None

    try:
        await update_job(job_id, "PRINTING")
        cups_options = {
            "copies": job_summary.get("copies", 1),
            "color": str(job_summary.get("color", "BW")).upper() != "BW",
        }
        cups_job_id = await cups_service.submit_to_cups(file_path, printer_name, cups_options)
        cups_job_id_str = str(cups_job_id)
        logger.info(
            "Job %s submitted to CUPS queue=%s cups_job_id=%s file=%s",
            job_id,
            printer_name,
            cups_job_id_str,
            file_path,
        )
        await update_job(job_id, "PRINTING", cups_job_id=cups_job_id_str)
        await cloud_api.mark_printing_started(job_id, cups_job_id_str, printer_name)
        result = await cups_service.wait_for_cups_job(cups_job_id)

        final = "DONE" if result == "DONE" else "FAILED"
        await update_job(job_id, final)
        if final == "DONE":
            await cloud_api.mark_completed(job_id, cups_job_id_str)
        else:
            await cloud_api.mark_failed(
                job_id,
                cups_job_id=cups_job_id_str,
                failure_code="CUPS_FAILED",
                failure_message="CUPS reported a failed print job.",
                is_retryable=False,
            )
    except Exception as exc:
        await update_job(job_id, "FAILED", error_msg=str(exc))
        try:
            await cloud_api.mark_failed(
                job_id,
                cups_job_id=cups_job_id_str,
                failure_code="PRINT_FAILED",
                failure_message=str(exc),
                is_retryable=False,
            )
        except Exception:
            pass
    finally:
        should_cleanup = True
        if settings.keep_failed_job_files:
            job_state = await get_job(job_id)
            if job_state and job_state["status"] == "FAILED":
                should_cleanup = False

        if job_dir.exists() and should_cleanup:
            shutil.rmtree(job_dir, ignore_errors=True)
        elif job_dir.exists():
            logger.warning("Keeping failed job files for debug: %s", job_dir)
