"""Downloads a released PDF through the PrintNest device file endpoint."""

from pathlib import Path

from app.config import settings
from app.services import cloud_api


async def download_file(job_id: str, file_token: str) -> Path:
    """Stream-download the released PDF into /tmp/printjobs/<job_id>/job.pdf."""
    job_dir = Path(settings.temp_dir) / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    file_path = job_dir / "job.pdf"
    await cloud_api.download_pdf(job_id, file_token, file_path)

    return file_path
