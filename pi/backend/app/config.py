from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # PrintNest backend
    cloud_api_url: str
    device_id: str
    shared_secret: str
    store_id: str | None = None

    # CUPS printer names - run `lpstat -p` on the Pi to find these
    document_printer_name: str
    photo_printer_name: str | None = None

    # Local temp storage - print-and-delete, never accumulates
    temp_dir: str = "/tmp/printjobs"

    # Heartbeat
    heartbeat_interval: int = 60

    # Debugging aid: keep failed job files on disk for inspection.
    # Set KEEP_FAILED_JOB_FILES=true in .env when troubleshooting CUPS failures.
    keep_failed_job_files: bool = False


settings = Settings()
